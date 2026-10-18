from aiogram import Router

from . import broadcasts, chats, leads, menu, more, rules, templates


def build_router() -> Router:
    root = Router()
    for module in (menu, rules, templates, broadcasts, chats, leads, more):
        root.include_router(module.router)
    return root
