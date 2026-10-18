from aiogram.fsm.state import State, StatesGroup


class Input(StatesGroup):
    rule_name = State()
    rule_rename = State()
    rule_kw = State()
    rule_ex = State()
    rule_cd = State()
    rule_test = State()

    tpl_name = State()
    tpl_content = State()
    tpl_rename = State()

    bc_name = State()
    bc_rename = State()
    bc_interval = State()
    bc_delay = State()

    picker_query = State()
    setting = State()
    admin_add = State()
