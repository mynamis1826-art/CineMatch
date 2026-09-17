"""CineMatch — a small, dependency-light movie recommendation MVP.

Developer: .echoren_
"""
import os
import asyncio
import random
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
    selected = []
    for item in ids.split(","):
        if not item:
            continue
        movie_id, _, rating = item.partition(":")
        selected.append((movie_id, int(rating or 0)))
    chosen = {movie_id for movie_id, _ in selected}
    if TMDB_KEY and selected:
        responses = await asyncio.gather(*[
            tmdb(f"/movie/{movie_id}/similar", {"page": 1})
            for movie_id, _ in selected
        ])
        ranked = {}
        for (movie_id, rating), result in zip(selected, responses):
            for movie in result:
                candidate_id = str(movie.get("id"))
                if candidate_id in chosen:
                    continue
                entry = ranked.setdefault(candidate_id, {"movie": movie, "score": 0})
                entry["score"] += 1 + rating / 10
        ordered = sorted(ranked.values(), key=lambda item: item["score"], reverse=True)
        return [normalize(item["movie"]) for item in ordered[:8]]
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

@app.get("/api/daily")
async def daily_movie():
    movies = await tmdb("/trending/movie/week", {})
    return normalize(random.choice(movies or FALLBACK))

@app.middleware("http")
async def add_musor_drop_ad(request, call_next):
    response = await call_next(request)
    if request.url.path != "/" or "text/html" not in response.headers.get("content-type", ""):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator]).decode("utf-8")
    ad = "<aside class='fixed bottom-5 left-4 z-20 hidden w-52 rounded-2xl border border-emerald-700 bg-gradient-to-br from-emerald-950 to-slate-900 p-4 text-white shadow-xl xl:block'><span class='text-[10px] uppercase tracking-widest text-emerald-400'>Реклама</span><h2 class='mt-2 text-lg font-bold'>Musor Drop</h2><p class='mt-1 text-xs leading-5 text-slate-300'>Приєднуйся до Musor Drop</p><a href='https://musor.best' target='_blank' rel='noopener noreferrer' class='mt-3 block w-full rounded-lg bg-emerald-500 px-3 py-2 text-center text-xs font-bold text-slate-950 hover:bg-emerald-400'>Дізнатися більше</a></aside>"
    ad = ad.replace("Приєднуйся до Musor Drop", "Musor Drop - твой шанс на большой дроп")
    return HTMLResponse(body.replace("</body>", ad + "</body>"), status_code=response.status_code)

@app.middleware("http")
async def add_daily_movie(request, call_next):
    response = await call_next(request)
    if request.url.path != "/" or "text/html" not in response.headers.get("content-type", ""):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator]).decode("utf-8")
    daily = "<aside class='fixed bottom-5 right-4 z-20 hidden w-52 rounded-2xl border border-amber-700 bg-gradient-to-br from-amber-950 to-slate-900 p-4 text-white shadow-xl xl:block'><span class='text-[10px] uppercase tracking-widest text-amber-400'>Фільм дня</span><div id='daily-movie' class='mt-2 text-sm text-slate-300'>Завантаження...</div></aside><script>fetch('/api/daily').then(r=>r.json()).then(m=>{document.getElementById('daily-movie').innerHTML=`${m.poster?`<img src='${m.poster}' alt='' class='mb-2 h-24 w-full rounded-lg object-cover'>`:''}<strong class='block text-sm text-white'>${m.title}</strong><span class='text-xs text-amber-300'>${m.year}</span>`}).catch(()=>{document.getElementById('daily-movie').textContent='Не вдалося завантажити';});</script>"
    return HTMLResponse(body.replace("</body>", daily + "</body>"), status_code=response.status_code)

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("""<!doctype html><html lang='uk'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>CineMatch</title><script src='https://cdn.tailwindcss.com'></script></head><body class='min-h-screen bg-slate-950 text-white'><aside class='fixed left-4 top-8 z-10 hidden w-44 rounded-2xl border border-fuchsia-900 bg-slate-900/95 p-3 shadow-xl xl:block'><h2 class='mb-3 text-sm font-bold text-fuchsia-300'>Популярне зараз</h2><div id='popular' class='space-y-3'><p class='text-xs text-slate-500'>Завантаження...</p></div></aside><aside class='fixed right-4 top-8 z-10 hidden w-44 rounded-2xl border border-cyan-900 bg-slate-900/95 p-3 shadow-xl xl:block'><h2 class='mb-3 text-sm font-bold text-cyan-300'>Новинки</h2><div id='new' class='space-y-3'><p class='text-xs text-slate-500'>Завантаження...</p></div></aside><main class='mx-auto max-w-5xl px-5 py-12'><header class='mb-10'><p class='mb-2 text-sm font-semibold uppercase tracking-[.3em] text-fuchsia-400'>CineMatch</p><h1 class='text-4xl font-bold md:text-6xl'>Фільм на цей вечір<br><span class='text-fuchsia-400'>знайдеться за секунди.</span></h1><p class='mt-4 max-w-xl text-slate-400'>Додайте улюблені стрічки — ми підберемо щось схоже.</p></header><section class='rounded-2xl border border-slate-800 bg-slate-900 p-5'><div class='flex gap-3'><input id='query' class='min-w-0 flex-1 rounded-xl bg-slate-800 px-4 py-3 outline-none ring-fuchsia-400 focus:ring-2' placeholder='Пошук фільму...' autocomplete='off'><button onclick='search()' class='rounded-xl bg-fuchsia-500 px-5 font-bold hover:bg-fuchsia-400'>Знайти</button></div><div id='results' class='mt-3'></div><div class='mt-6 flex items-center justify-between'><h2 class='font-bold'>Сподобалося <span id='count' class='text-fuchsia-400'>(0)</span></h2><button onclick='recommend()' class='rounded-xl bg-white px-5 py-3 font-bold text-slate-950 hover:bg-fuchsia-200'>Підібрати фільм ✨</button></div><div id='liked' class='mt-3 flex flex-wrap gap-2'></div></section><section class='mt-12'><h2 class='mb-5 text-2xl font-bold'>Рекомендації</h2><div id='cards' class='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'></div></section></main><script>
let liked=JSON.parse(localStorage.getItem('cinematch')||'[]'); const $=id=>document.getElementById(id);
function render(){ $('count').textContent=`(${liked.length})`; $('liked').innerHTML=liked.map((m,i)=>`<div class='rounded-xl bg-slate-800 px-3 py-2 text-sm'><div class='flex items-center gap-2'><span>${m.title}</span><button class='flex h-7 w-7 items-center justify-center rounded-full bg-red-500/20 text-lg font-bold text-red-200 transition hover:bg-red-500/30' onclick='removeMovie(${i})'>×</button></div><div class='mt-2 flex items-center gap-1'><span class='mr-1 text-xs text-slate-400'>Оцінка:</span>${Array.from({length:10},(_,n)=>`<button title='${n+1}/10' class='text-lg leading-none ${m.rating>=n+1?'text-amber-400':'text-slate-600'}' onclick='setRating(${i},${n+1})'>★</button>`).join('')}</div></div>`).join(''); localStorage.setItem('cinematch',JSON.stringify(liked)); }
function add(m){if(!liked.some(x=>x.id==m.id)){m.rating=0;liked.push(m);}render();}
function clearAll(){ if (!liked.length) return; if (!confirm('Удалити всі вибрані фільми?')) return; liked=[]; render(); }
function setRating(i,rating){liked[i].rating=rating;render();}
function removeMovie(i){liked.splice(i,1);render();}
async function getData(url){let response=await fetch(url);if(!response.ok)throw new Error('Request failed');return response.json();}
async function search(){let q=$('query').value.trim();if(!q)return;$('results').innerHTML='<p class="mt-3 text-slate-400">Пошук...</p>';try{let data=await getData('/api/search?q='+encodeURIComponent(q));$('results').innerHTML=data.length?data.map(m=>`<button class='mr-2 mt-2 rounded-lg bg-slate-800 px-3 py-2 text-left hover:bg-fuchsia-900' onclick='add(${JSON.stringify(m).replaceAll("'","&#39;")})'>＋ ${m.title} <small class='text-slate-400'>${m.year}</small></button>`).join(''):'<p class="mt-3 text-slate-400">Нічого не знайдено.</p>';}catch(error){$('results').innerHTML='<p class="mt-3 text-rose-400">Не вдалося виконати пошук. Перевірте підключення до сервера.</p>';}}
async function recommend(){if(!liked.length){alert('Спочатку додайте хоча б один фільм.');return}let ids=liked.map(x=>`${x.id}:${x.rating||0}`).join(',');$('cards').innerHTML='<p class="text-slate-400">Підбираємо фільми...</p>';try{let data=await getData('/api/recommendations?ids='+ids);$('cards').innerHTML=data.map(m=>`<article class='overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-5'><div class='mb-4 flex h-64 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-fuchsia-900 to-slate-800 text-5xl'>${m.poster?`<img src='${m.poster}' alt='${m.title}' class='h-full w-full object-cover' onerror="this.remove()">`:'🎬'}</div><h3 class='text-lg font-bold'>${m.title}</h3><p class='mt-1 text-sm text-fuchsia-300'>${m.year} · ${m.genre}</p><p class='mt-3 text-sm leading-6 text-slate-400'>${m.overview}</p></article>`).join('')||'<p class="text-slate-400">Спробуйте додати інший фільм.</p>';}catch(error){$('cards').innerHTML='<p class="text-rose-400">Не вдалося отримати рекомендації. Перевірте підключення до сервера.</p>';}}
function renderSidebar(id,movies){$(id).innerHTML=movies.map(m=>`<div class='flex items-center gap-2'><div class='h-14 w-10 shrink-0 overflow-hidden rounded bg-slate-800'>${m.poster?`<img src='${m.poster}' alt='' class='h-full w-full object-cover'>`:'🎬'}</div><span class='text-xs leading-4 text-slate-300'>${m.title}</span></div>`).join('');}
function addUiPolish(){
    const heading=$('count')?.parentElement;
    const recommendButton=heading?.parentElement?.querySelector("button[onclick='recommend()']");
    let clearButton=$('clear-all');
    if(recommendButton)recommendButton.classList.toggle('hidden',liked.length===0);
    if(recommendButton&&!clearButton){clearButton=document.createElement('button');clearButton.id='clear-all';clearButton.textContent='Удалить всё';clearButton.className='mr-3 rounded-xl border border-fuchsia-500/50 bg-fuchsia-500/10 px-4 py-2 text-sm font-semibold text-fuchsia-200 hover:bg-fuchsia-500/20';clearButton.onclick=clearAll;recommendButton.parentElement.insertBefore(clearButton,recommendButton);}
    if(clearButton)clearButton.classList.toggle('hidden',liked.length<=3);
    document.querySelectorAll("#liked button[onclick^='removeMovie']").forEach(button=>{button.className='flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-fuchsia-500/20 text-xl font-bold leading-none text-fuchsia-200 ring-1 ring-fuchsia-400/30 transition hover:bg-fuchsia-500/30';});
}
const originalRender=render;
render=function(){originalRender();addUiPolish();};
const originalSearch=search;
search=async function(){await originalSearch();document.querySelectorAll('#results button[onclick^="add("]').forEach(button=>{const movieId=button.getAttribute('onclick').match(/"id":(\d+)/)?.[1];if(movieId&&!button.nextElementSibling?.matches('a'))button.insertAdjacentHTML('afterend',`<a href='https://www.themoviedb.org/movie/${movieId}' target='_blank' rel='noopener noreferrer' class='inline-flex shrink-0 rounded-lg border border-fuchsia-500/50 bg-fuchsia-500/10 px-2 py-1 text-[10px] font-semibold text-fuchsia-200 hover:bg-fuchsia-500/20'>Подробнее</a>`);const link=button.nextElementSibling;if(link?.matches('a')){const row=document.createElement('div');row.className='mt-2 flex min-w-0 items-center gap-2';button.className='min-w-0 flex-1 truncate rounded-lg bg-slate-800 px-3 py-2 text-left hover:bg-fuchsia-900';button.parentElement.insertBefore(row,button);row.append(button,link);}});};
recommend=async function(){if(!liked.length){alert('Спочатку додайте хоча б один фільм.');return;}const ids=liked.map(x=>`${x.id}:${x.rating||0}`).join(',');$('cards').innerHTML='<p class="text-slate-400">Підбираємо фільми...</p>';try{const data=await getData('/api/recommendations?ids='+ids);$('cards').innerHTML=data.map(m=>`<article class='overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 p-5'><div class='mb-4 flex h-64 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-fuchsia-900 to-slate-800 text-5xl'>${m.poster?`<img src='${m.poster}' alt='${m.title}' class='h-full w-full object-cover'>`:'🎬'}</div><h3 class='text-lg font-bold'>${m.title}</h3><p class='mt-1 text-sm text-fuchsia-300'>${m.year} · ${m.genre}</p><p class='mt-3 text-sm leading-6 text-slate-400'>${m.overview}</p><a href='https://www.themoviedb.org/movie/${m.id}' target='_blank' rel='noopener noreferrer' class='mt-4 inline-flex rounded-lg border border-fuchsia-500/50 bg-fuchsia-500/10 px-3 py-2 text-sm font-semibold text-fuchsia-200 hover:bg-fuchsia-500/20'>Подробнее</a></article>`).join('')||'<p class="text-slate-400">Спробуйте додати інший фільм.</p>';}catch(error){$('cards').innerHTML='<p class="text-rose-400">Не вдалося отримати рекомендації. Перевірте підключення до сервера.</p>';}};
async function loadSidebar(){try{let data=await getData('/api/sidebar');renderSidebar('popular',data.popular);renderSidebar('new',data.new);}catch(error){$('popular').innerHTML=$('new').innerHTML='<p class="text-xs text-slate-500">Не вдалося завантажити.</p>';}}
render();loadSidebar();$('query').addEventListener('keydown',e=>{if(e.key==='Enter')search()});
</script></body></html>""")     
