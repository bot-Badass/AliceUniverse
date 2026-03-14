from aiogram.fsm.state import State, StatesGroup

class AddLeadStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_phone = State()  # Если скрыт
    confirm_data = State()
    waiting_edit_field = State()
    waiting_edit_value = State()

class WorkCardStates(StatesGroup):
    in_call = State()
    waiting_result = State()
    thinking_set_date = State()
    appointment_set_date = State()
    adding_notes = State()
    edit_field = State()
    edit_value = State()

class SearchStates(StatesGroup):
    waiting_query = State()
    showing_results = State()


class ReminderStates(StatesGroup):
    waiting_datetime = State()
