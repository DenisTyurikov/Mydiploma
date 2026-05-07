import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib

def train_on_real_data():
    print("1. Загрузка реальных пространственных данных...")
    try:
        df = pd.read_csv("real_city_dataset.csv")
    except FileNotFoundError:
        print("❌ Ошибка: Файл 'real_city_dataset.csv' не найден. Сначала запустите скрипт парсинга города.")
        return

    # Базовые колонки, которые собирает наш Telegram-бот
    base_features = ['residential', 'transport', 'medical', 'supermarkets', 'offices', 'education', 'parks']

    print("2. Обучение модели для АПТЕКИ (Pharmacy)...")
    # Считаем балл (используем реальную колонку pharmacy_comp из CSV)
    y_pharmacy = (df['medical']*30 + df['residential']*10 + df['supermarkets']*10 - df['pharmacy_comp']*25)
    y_pharmacy = (y_pharmacy + np.random.normal(0, 5, len(df))).clip(0, 100)

    # Выделяем нужные колонки и ПЕРЕИМЕНОВЫВАЕМ конкурентов под стандарт бота
    X_pharmacy = df[base_features + ['pharmacy_comp']].rename(columns={'pharmacy_comp': 'competitors'})

    model_pharmacy = RandomForestRegressor(n_estimators=100, random_state=42)
    model_pharmacy.fit(X_pharmacy, y_pharmacy)
    joblib.dump(model_pharmacy, 'model_pharmacy.pkl')


    print("3. Обучение модели для КОФЕЙНИ (Cafe)...")
    y_cafe = (df['offices']*20 + df['education']*25 + df['parks']*15 + df['transport']*10 - df['cafe_comp']*20)
    y_cafe = (y_cafe + np.random.normal(0, 5, len(df))).clip(0, 100)

    X_cafe = df[base_features + ['cafe_comp']].rename(columns={'cafe_comp': 'competitors'})

    model_cafe = RandomForestRegressor(n_estimators=100, random_state=42)
    model_cafe.fit(X_cafe, y_cafe)
    joblib.dump(model_cafe, 'model_cafe.pkl')


    print("4. Обучение модели для ПВЗ (PVZ)...")
    y_pvz = (df['residential']*25 + df['transport']*5 - df['pvz_comp']*30)
    y_pvz = (y_pvz + np.random.normal(0, 5, len(df))).clip(0, 100)

    X_pvz = df[base_features + ['pvz_comp']].rename(columns={'pvz_comp': 'competitors'})

    model_pvz = RandomForestRegressor(n_estimators=100, random_state=42)
    model_pvz.fit(X_pvz, y_pvz)
    joblib.dump(model_pvz, 'model_pvz.pkl')

    print("✅ Все 3 модели успешно обучены на реальных данных и сохранены!")

if __name__ == "__main__":
    train_on_real_data()