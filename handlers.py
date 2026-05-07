import os
import pandas as pd
import h3
import joblib
import folium
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from geo_api import get_geo_data

router = Router()


# 1. Создаем класс состояний (наши шаги диалога)
class GeoAnalysis(StatesGroup):
    choosing_business = State()  # Шаг 1: Пользователь выбирает тип бизнеса
    waiting_for_location = State()  # Шаг 2: Пользователь отправляет локацию


# Функция для клавиатуры выбора бизнеса (Inline)
def get_business_keyboard():
    kb = [
        [InlineKeyboardButton(text="☕ Кофейня", callback_data="business_cafe")],
        [InlineKeyboardButton(text="💊 Аптека", callback_data="business_pharmacy")],
        [InlineKeyboardButton(text="📦 ПВЗ (Пункты выдачи)", callback_data="business_pvz")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# Функция для клавиатуры отправки локации (Reply)
def get_location_keyboard():
    kb = [[KeyboardButton(text="📍 Отправить локацию", request_location=True)]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# --- ОБРАБОТЧИКИ ---

# Шаг 0: Команда /start
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()  # Очищаем память, если вдруг там что-то зависло с прошлого раза

    await message.answer(
        "Привет! Я ГИС-бот для анализа локаций.\n"
        "Выбери тип бизнеса, который хочешь открыть:",
        reply_markup=get_business_keyboard()
    )
    # Переводим бота в состояние ожидания выбора бизнеса
    await state.set_state(GeoAnalysis.choosing_business)


# Шаг 1: Обработка нажатия на Inline-кнопку
@router.callback_query(GeoAnalysis.choosing_business, F.data.startswith("business_"))
async def handle_business_choice(callback: CallbackQuery, state: FSMContext):
    # Извлекаем тип бизнеса из callback_data (например, "cafe" из "business_cafe")
    business_type = callback.data.split("_")[1]

    # ЗАПОМИНАЕМ выбор в оперативной памяти бота
    await state.update_data(chosen_business=business_type)

    # Словарь для красивого вывода названия
    business_names = {
        "cafe": "Кофейня",
        "pharmacy": "Аптека",
        "pvz": "Пункт выдачи (ПВЗ)"
    }
    human_name = business_names.get(business_type, "Неизвестно")

    # Обязательно отвечаем на callback, чтобы кнопка перестала "моргать" (часики загрузки)
    await callback.answer()

    await callback.message.answer(
        f"✅ Вы выбрали направление: **{human_name}**.\n\n"
        f"Теперь отправьте мне локацию (точку на карте) для анализа этого района.",
        reply_markup=get_location_keyboard()
    )
    # Переводим бота на следующий шаг
    await state.set_state(GeoAnalysis.waiting_for_location)


# Шаг 2: Обработка локации
@router.message(GeoAnalysis.waiting_for_location, F.location)
async def handle_location(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude

    user_data = await state.get_data()
    business_type = user_data.get("chosen_business")

    msg = await message.answer(f"🔍 Сканирую район (радиус 1.5 км)...\nЭто займет около 10-20 секунд ⏳")

    # 1. Сбор данных
    geo_data = await get_geo_data(business_type, lat, lon)
    if geo_data is None:
        await msg.edit_text("❌ Ошибка при сборе данных с карт.")
        await state.clear()
        return

    await msg.edit_text("✅ Данные собраны! ИИ анализирует локацию и рисует карту...")

    # 2. Построение сетки H3 и распределение объектов
    try:
        center_hex = h3.latlng_to_cell(lat, lon, 9)
        hex_grid = list(h3.grid_disk(center_hex, 10))
    except AttributeError:
        center_hex = h3.geo_to_h3(lat, lon, 9)
        hex_grid = list(h3.k_ring(center_hex, 10))

    hex_data = {
        h: {"residential": 0, "transport": 0, "medical": 0,
            "supermarkets": 0, "offices": 0, "education": 0,
            "parks": 0, "competitors": 0} for h in hex_grid
    }

    def assign_to_hexagons(category_name, items_list):
        for item in items_list:
            i_lat = item.get('center', {}).get('lat') or item.get('lat')
            i_lon = item.get('center', {}).get('lon') or item.get('lon')
            if i_lat and i_lon:
                try:
                    h_id = h3.latlng_to_cell(i_lat, i_lon, 9)
                except AttributeError:
                    h_id = h3.geo_to_h3(i_lat, i_lon, 9)
                if h_id in hex_data:
                    hex_data[h_id][category_name] += 1

    for category, items in geo_data.items():
        assign_to_hexagons(category, items)

    # Формируем DataFrame
    data_for_df = []
    for h_id, stats in hex_data.items():
        row = {'hex_id': h_id}
        row.update(stats)
        data_for_df.append(row)

    df = pd.DataFrame(data_for_df)

    # --- НОВЫЙ БЛОК: МАШИННОЕ ОБУЧЕНИЕ (ИНФЕРЕНС) ---

    # Загружаем нужную модель в зависимости от выбора
    model_path = f"model_{business_type}.pkl"
    try:
        model = joblib.load(model_path)
    except FileNotFoundError:
        await msg.edit_text(f"❌ Файл модели {model_path} не найден! Убедитесь, что вы запустили скрипт обучения.")
        await state.clear()
        return

    # Выделяем только те колонки признаков, на которых модель училась
    feature_cols = ['residential', 'transport', 'medical', 'supermarkets', 'offices', 'education', 'parks',
                    'competitors']
    X_predict = df[feature_cols]

    # Делаем предсказание!
    df['success_score'] = model.predict(X_predict)

    # --- НОВЫЙ БЛОК: ОТРИСОВКА КАРТЫ С FOLIUM ---

    # Создаем базовую карту, отцентрированную по точке пользователя
    m = folium.Map(location=[lat, lon], zoom_start=14, tiles="CartoDB positron")

    # Проходимся по всем гексагонам и рисуем их на карте
    for index, row in df.iterrows():
        h_id = row['hex_id']
        score = row['success_score']

        # Получаем координаты углов гексагона для отрисовки полигона
        try:
            boundary = h3.cell_to_boundary(h_id)
        except AttributeError:
            boundary = h3.h3_to_geo_boundary(h_id)

        # Логика цветов: Зеленый (>70), Желтый (40-70), Красный (<40)
        if score >= 70:
            fill_color = '#00FF00'  # Зеленый
        elif score >= 40:
            fill_color = '#FFFF00'  # Желтый
        else:
            fill_color = '#FF0000'  # Красный

        # Рисуем полигон
        folium.Polygon(
            locations=boundary,
            color='black',  # Цвет границ
            weight=1,  # Толщина границ
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.4,  # Прозрачность заливки
            tooltip=f"Оценка ИИ: {score:.1f}/100<br>Конкурентов: {row['competitors']}"  # Всплывающая подсказка
        ).add_to(m)

    # Сохраняем карту в HTML
    map_filename = f"map_{business_type}_{lat}_{lon}.html"
    m.save(map_filename)

    # Сохраняем датасет в CSV
    csv_filename = f"dataset_{business_type}_{lat}_{lon}.csv"
    df.to_csv(csv_filename, index=False)

    # Отправляем результаты пользователю
    map_doc = FSInputFile(map_filename)
    csv_doc = FSInputFile(csv_filename)

    await msg.delete()
    await message.answer(f"🏆 ГИС-анализ и ML-прогнозирование завершены!\n\n"
                         f"Откройте прикрепленный `.html` файл в любом браузере, чтобы увидеть интерактивную карту.\n"
                         f"🟩 Зеленые зоны — идеальное место для открытия.\n"
                         f"🟥 Красные зоны — высокий риск.")

    await message.answer_document(map_doc)
    await message.answer_document(csv_doc)

    # Удаляем временные файлы
    os.remove(map_filename)
    os.remove(csv_filename)
    await state.clear()