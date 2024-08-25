# Built-ins
import base64
import ast

# Downloaded
import requests

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import redis

# Project
from stats_gather import data_pickup
from stats_gather import s_utils


CACHE_RETENTION: int = 60 * 5

db: redis.Redis = redis.Redis("localhost", port=6379, decode_responses=True)

# Disabling the default routes
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, swagger_ui_oauth2_redirect_url=None)

# Mounting all the directories
app.mount("/style", StaticFiles(directory="./templates/assets/stylesheet"), name="style")
app.mount("/images", StaticFiles(directory="./templates/assets/images"), name="images")
app.mount("/font", StaticFiles(directory="./templates/assets/font"), name="font")
app.mount("/video", StaticFiles(directory="./templates/assets/video"), name="video")
app.mount("/script", StaticFiles(directory="./templates/assets/scripts"), name="script")

templates = Jinja2Templates(directory="templates", trim_blocks=True, lstrip_blocks=True)


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/{page}")
async def wrong_scheme(request: Request, page: str):
    if page == "info":
        return templates.TemplateResponse("info.html", {"request": request})

    return templates.TemplateResponse("home.html",
                                      {"request": request,
                                       "message": "To view a player's profile, use the search bar."})


@app.get("/p/{name}")
async def stats(request: Request, name: str, profile: str = "selected"):
    """
    Return the page with the player's statistics for its currently selected profile
    :param request: Request data
    :param name: The player's name (not case-sensitive)
    :param profile: Set to "selected" to specify that the retrieved data will be for the selected profile
    :return:
    """
    player_data = requests.get(f"https://playerdb.co/api/player/minecraft/{name}")
    # If this Minecraft account doesn't exist → 404 Not Found
    if not player_data.ok:
        return templates.TemplateResponse("home.html",
                                          {"request": request,
                                           "message": f"Minecraft account not found for {name}"})

    player_data = player_data.json()
    _uuid: str = player_data['data']['player']['id']

    skin_link: str = f"https://crafthead.net/avatar/{_uuid}/256"

    p = data_pickup.Profile(uuid=_uuid)

    # Check if this profile is already stored in cache
    if db.get(f"{name.lower()}:stats") is not None:
        player_stats = db.get(f"{name.lower()}:stats")
        player_rank = db.get(f"{name.lower()}:rank")

        p.data = ast.literal_eval(base64.b64decode(player_stats).decode())
        p.rank_data = ast.literal_eval(base64.b64decode(player_rank).decode())

        p.gather_rank()
        result = True
    else:
        p.gather_rank()  # Send API request to fetch the player's Hypixel rank (and a list of SkyBlock profiles)
        result = p.gather_stats()  # Send API request to Hypixel to fetch the player's stats

        # Caching the API data
        db.set(f"{name.lower()}:stats", base64.b64encode(str(p.data).encode()), ex=CACHE_RETENTION)
        db.set(f"{name.lower()}:rank", base64.b64encode(str(p.rank_data).encode()), ex=CACHE_RETENTION)

    if not result:
        return templates.TemplateResponse("home.html",
                                          {"request": request,
                                           "message": "An error occurred during the Hypixel API request"})

    context = s_utils.get_context_for_profile(player=p, profile_name=profile)

    # Filling the context with local variables
    context['request'] = request
    context['player_name'] = name
    context['player_uuid'] = _uuid
    context['skin_link'] = skin_link
    context['displayed_profile'] = profile.lower().capitalize()

    return templates.TemplateResponse("stats.html", context=context)


@app.get("/p/{name}/{profile}")
async def stats_2(request: Request, name: str, profile: str):
    """
    Return the page with the player's statistics for a specified profile
    :param request: Request data
    :param name: The player's name (not case-sensitive)
    :param profile: Name of the targeted profile (not case-sensitive)
    :return:
    """
    return await stats(request=request, name=name, profile=profile.lower().capitalize())
