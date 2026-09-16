"""CineMatch — a small, dependency-light movie recommendation MVP.

Run with: uvicorn CineMatch:app --reload
Optional: set TMDB_API_KEY to enable live search and recommendations.
"""
import os
import asyncio
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI(title="CineMatch")
TMDB_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_URL = "https://api.themoviedb.org/3"

FALLBACK = [
    {"id": 1, "title": "The Grand Budapest Hotel", "year": 2014, "genre": "Комедія, Драма", "overview": "Барвиста історія легендарного консьєржа та його юного помічника."},
    {"id": 2, "title": "Knives Out", "year": 2019, "genre": "Детектив, Комедія", "overview": "Детектив розплутує загадкову смерть письменника у дивній родині."},
    {"id": 3, "title": "Interstellar", "year": 2014, "genre": "Фантастика, Драма", "overview": "Команда астронавтів вирушає крізь червоточину, щоб врятувати людство."},
    {"id": 4, "title": "The Dark Knight", "year": 2008, "genre": "Бойовик, Кримінал", "overview": "Бетмен протистоїть небезпечному злочинцю, який сіє хаос у Ґотемі."},
    {"id": 5, "title": "Spirited Away", "year": 2001, "genre": "Мультфільм, Фентезі", "overview": "Дівчинка потрапляє до чарівного світу й шукає шлях додому."},
]

async def tmdb(path: str, params: dict[str, Any], language: str = "uk-UA") -> list[dict[str, Any]]:
    if not TMDB_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            response = await client.get(f"{TMDB_URL}{path}", params={"api_key": TMDB_KEY, "language": language, **params})
            response.raise_for_status()
            return response.json().get("results", [])
    except (httpx.HTTPError, ValueError):
        return []

def normalize(movie: dict[str, Any]) -> dict[str, Any]:
    return {"id": movie.get("id"), "title": movie.get("title") or movie.get("name", "Без назви"),
            "year": (movie.get("release_date") or "")[:4] or "—", "genre": "Кіно",
            "overview": movie.get("overview") or "Опис поки що недоступний.",
            "poster": ("https://image.tmdb.org/t/p/w342" + movie["poster_path"]) if movie.get("poster_path") else ""}

@app.get("/api/search")
async def search(q: str = Query(min_length=1)):
    title_requests = [
        tmdb("/search/movie", {"query": q, "page": 1, "include_adult": False}, language)
        for language in ("uk-UA", "ru-RU", "en-US")
    ]
    keyword_requests = [
        tmdb("/search/keyword", {"query": q, "page": 1}, language)
        for language in ("uk-UA", "ru-RU", "en-US")
    ]
    title_responses, keyword_responses = await asyncio.gather(
        asyncio.gather(*title_requests), asyncio.gather(*keyword_requests)
    )
    title_movies = [movie for response in title_responses for movie in response]
    keyword_ids = list({str(keyword.get("id")) for response in keyword_responses for keyword in response if keyword.get("id")})
    keyword_movies = await tmdb(
        "/discover/movie",
        {"with_keywords": "|".join(keyword_ids[:5]), "sort_by": "popularity.desc", "page": 1},
    ) if keyword_ids else []
    live = list({str(movie.get("id")): movie for movie in [*title_movies, *keyword_movies]}.values())
    if live:
        return [normalize(x) for x in live[:8]]
    return [x for x in FALLBACK if q.lower() in x["title"].lower()][:8]

@app.get("/api/recommendations")
async def recommendations(ids: str = ""):
    chosen = [x for x in ids.split(",") if x]
    if TMDB_KEY and chosen:
        result = await tmdb(f"/movie/{chosen[0]}/similar", {"page": 1})
        return [normalize(x) for x in result[:5] if str(x.get("id")) not in chosen]
    return [x for x in FALLBACK if str(x["id"]) not in chosen][:5]

@app.get("/api/sidebar")
async def sidebar():
    popular, new = await asyncio.gather(
        tmdb("/trending/movie/week", {}),
        tmdb("/movie/now_playing", {"page": 1}),
    )
    return {
        "popular": [normalize(movie) for movie in (popular or FALLBACK)[:4]],
        "new": [normalize(movie) for movie in (new or FALLBACK[1:])[:4]],
    }

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("""<!doctype html><html lang='uk'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>CineMatch</title><script src='https://cdn.tailwindcss.com'></script></head><body class='min-h-screen bg-slate-950 text-white'><aside class='fixed left-4 top-8 z-10 hidden w-44 rounded-2xl border border-fuchsia-900 bg-slate-900/95 p-3 shadow-xl xl:block'><h2 class='mb-3 text-sm font-bold text-fuchsia-300'>Популярне зараз</h2><div id='popular' class='space-y-3'><p class='text-xs text-slate-500'>Завантаження...</p></div></aside><aside class='fixed right-4 top-8 z-10 hidden w-44 rounded-2xl border border-cyan-900 bg-slate-900/95 p-3 shadow-xl xl:block'><h2 class='mb-3 text-sm font-bold text-cyan-300'>Новинки</h2><div id='new' class='space-y-3'><p class='text-xs text-slate-500'>Завантаження...</p></div></aside><main class='mx-auto max-w-5xl px-5 py-12'><header class='mb-10'><p class='mb-2 text-sm font-semibold uppercase tracking-[.3em] text-fuchsia-400'>CineMatch</p><h1 class='text-4xl font-bold md:text-6xl'>Фільм на цей вечір<br><span class='text-fuchsia-400'>знайдеться за секунди.</span></h1><p class='mt-4 max-w-xl text-slate-400'>Додайте улюблені стрічки — ми підберемо щось схоже.</p></header><section class='rounded-2xl border border-slate-800 bg-slate-900 p-5'><div class='flex gap-3'><input id='query' class='min-w-0 flex-1 rounded-xl bg-slate-800 px-4 py-3 outline-none ring-fuchsia-400 focus:ring-2' placeholder='Пошук фільму...' autocomplete='off'><button onclick='search()' class='rounded-xl bg-fuchsia-500 px-5 font-bold hover:bg-fuchsia-400'>Знайти</button></div><div id='results' class='mt-3'></div><div class='mt-6 flex items-center justify-between'><h2 class='font-bold'>Сподобалося <span id='count' class='text-fuchsia-400'>(0)</span></h2><button onclick='recommend()' class='rounded-xl bg-white px-5 py-3 font-bold text-slate-950 hover:bg-fuchsia-200'>Підібрати фільм ✨</button></div><div id='liked' class='mt-3 flex flex-wrap gap-2'></div></section><section class='mt-12'><h2 class='mb-5 text-2xl font-bold'>Рекомендації</h2><div id='cards' class='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'></div></section></main><script>
let liked=JSON.parse(localStorage.getItem('cinematch')||'[]'); const $=id=>document.getElementById(id);
function render(){ $('count').textContent=`(${liked.length})`; $('liked').innerHTML=liked.map((m,i)=>`<span class='rounded-full bg-slate-800 px-3 py-2 text-sm'>${m.title}<button class='ml-2 text-fuchsia-400' onclick='removeMovie(${i})'>×</button></span>`).join(''); localStorage.setItem('cinematch',JSON.stringify(liked)); }
function add(m){if(!liked.some(x=>x.id==m.id))liked.push(m);render();$('results').innerHTML='';}
function removeMovie(i){liked.splice(i,1);render();}
async function getData(url){let response=await fetch(url);if(!response.ok)throw new Error('Request failed');return response.json();}
async function search(){let q=$('query').value.trim();if(!q)return;$('results').innerHTML='<p class="mt-3 text-slate-400">Пошук...</p>';try{let data=await getData('/api/search?q='+encodeURIComponent(q));$('results').innerHTML=data.length?data.map(m=>`<button class='mr-2 mt-2 rounded-lg bg-slate-800 px-3 py-2 text-left hover:bg-fuchsia-900' onclick='add(${JSON.stringify(m).replaceAll("'","&#39;")})'>＋ ${m.title} <small class='text-slate-400'>${m.year}</small></button>`).join(''):'<p class="mt-3 text-slate-400">Нічого не знайдено.</p>';}catch(error){$('results').innerHTML='<p class="mt-3 text-rose-400">Не вдалося виконати пошук. Перевірте підключення до сервера.</p>';}}
async function recommend(){if(!liked.length){alert('Спочатку додайте хоча б один фільм.');return}let ids=liked.map(x=>x.id).join(',');$('cards').innerHTML='<p class="text-slate-400">Підбираємо фільми...</p>';try{let data=await getData('/api/recommendations?ids='+ids);$('cards').innerHTML=data.map(m=>`<article class='overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-5'><div class='mb-4 flex h-64 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-fuchsia-900 to-slate-800 text-5xl'>${m.poster?`<img src='${m.poster}' alt='${m.title}' class='h-full w-full object-cover' onerror="this.remove()">`:'🎬'}</div><h3 class='text-lg font-bold'>${m.title}</h3><p class='mt-1 text-sm text-fuchsia-300'>${m.year} · ${m.genre}</p><p class='mt-3 text-sm leading-6 text-slate-400'>${m.overview}</p></article>`).join('')||'<p class="text-slate-400">Спробуйте додати інший фільм.</p>';}catch(error){$('cards').innerHTML='<p class="text-rose-400">Не вдалося отримати рекомендації. Перевірте підключення до сервера.</p>';}}
function renderSidebar(id,movies){$(id).innerHTML=movies.map(m=>`<div class='flex items-center gap-2'><div class='h-14 w-10 shrink-0 overflow-hidden rounded bg-slate-800'>${m.poster?`<img src='${m.poster}' alt='' class='h-full w-full object-cover'>`:'🎬'}</div><span class='text-xs leading-4 text-slate-300'>${m.title}</span></div>`).join('');}
async function loadSidebar(){try{let data=await getData('/api/sidebar');renderSidebar('popular',data.popular);renderSidebar('new',data.new);}catch(error){$('popular').innerHTML=$('new').innerHTML='<p class="text-xs text-slate-500">Не вдалося завантажити.</p>';}}
render();loadSidebar();$('query').addEventListener('keydown',e=>{if(e.key==='Enter')search()});
</script></body></html>""")
