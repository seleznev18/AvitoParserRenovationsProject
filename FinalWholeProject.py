print("Установка необходимых библиотек:")
import shutil
from torch.utils.data import Dataset, DataLoader
import torch
from transformers import ViltProcessor, ViltForQuestionAnswering
from torch.optim import AdamW
from tqdm import tqdm
from PIL import Image
import os
import torch.nn as nn
from torchvision import transforms
import subprocess
from transformers import logging
import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import BytesIO
import time
logging.set_verbosity_error()

# Запускаем приложение
process = subprocess.Popen(['C:/Parser_Task/Final_thing/FinalWholeProject/parser_avito_2_1_0.exe'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print('Скрипт запущен, для начала работы настройте AvitoParser, выполните поиск и закройте приложение')
try:
    process.wait(timeout=100) 
except subprocess.TimeoutExpired:
    process.kill()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("Далее будет произведено развертывание необходимых для работы моделей")
print("Развертывание модели Inside_Outside:")

shutil.unpack_archive("saved_model_Inside_Outside.zip", "./restored_model_Inside_Outside", "zip")
model_Inside_Oustside = ViltForQuestionAnswering.from_pretrained("./restored_model_Inside_Outside").to(device)
processor_Inside_Oustside = ViltProcessor.from_pretrained("./restored_model_Inside_Outside")
prompt_Inside_Outside="Is the image taken from inside the apartment, or does it show the building's exterior?"
class_names_Inside_Outside = ["Inside the apartment", "Outside the building"]

print("Развертывание модели Renovations_model:")

shutil.unpack_archive("saved_model_renovations.zip", "./restored_model_renovations", "zip")
model_renovations = ViltForQuestionAnswering.from_pretrained("./restored_model_renovations").to(device)
processor_renovations = ViltProcessor.from_pretrained("./restored_model_renovations")
prompt_renovations="Classify this apartment image as one of the following categories: Designer renovation, Old renovation, or No renovation."
class_names_renovations = ["No renovation", "Old renovation", "Designer renovation"]

# Функция предсказания
def predict_vilt(model, processor, image_path, prompt, transform, device):
    # Загрузка и преобразование изображения
    image = Image.open(image_path).convert("RGB")  # Открываем изображение
    image = transform(image)                      # Применяем преобразования
    image = image.mul(255).byte()                 # Преобразуем значения в [0-255]
    image = image.unsqueeze(0)                    # Добавляем batch dimension

    # Подготовка данных для модели
    inputs = processor(
        images=[image.squeeze(0)],  # Передаём список изображений
        text=[prompt],              # Передаём список с текстом
        return_tensors="pt",
        padding=True
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}  # Переносим тензоры на устройство

    # Прогон через модель
    model.eval()
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        preds = torch.argmax(logits, dim=1)
    return preds.item()  # Возвращаем предсказанный класс

# Трансформации изображения
image_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])

print("Далее для найденных квартир будут произведены следующие операции: 1)скачивание фото с объявления, 2)отбор фото, показывающих квартиру изнутри, 3)Усреднение результатов прогона фото через основную модель, для получения общего вердикта о ремонте данной квартиры.")

## Открытие xlsx таблицы с данными объявлений
excel = pd.read_excel('C:/Parser_Task/Final_thing/FinalWholeProject/result/all.xlsx')
excel = excel.drop(['Просмотров', 'Дата публикации','Продавец', 'Адрес'], axis=1)
names = excel.iloc[:,2].tolist()
headers = {'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.72 Safari/537.36'}
renovations_verdicts=[]


for j,url in enumerate(tqdm(names,desc="Processing")):
    # Отправляем GET-запрос к странице с заголовками
    response = requests.get(url,"html.parser", headers=headers)

    # Если запрос успешен, продолжаем
    if response.status_code == 200:
        curr_images=[]
        # Парсим содержимое страницы
        soup = BeautifulSoup(response.text, 'html.parser')
        # Находим все теги img
        images = soup.find_all('img')
        # В этом цикле скачиваются все изображения с данного объявления
        for img in images:
            img_src = img.get('src')
            if img_src:
                try:
                    img_response=requests.get(img_src)
                    if img_response.status_code== 200:
                        curr_images.append(BytesIO(img_response.content))
                except Exception as e:
                    continue
        if len(curr_images)==0:
            renovations_verdicts.append("Не удалось скачать изображения")
        else:
            #Отбор изображений внутри квартиры
            curr_imgs_inside=[]
            for img in curr_images:
                curr_predict_inside_outside=class_names_Inside_Outside[predict_vilt(model_Inside_Oustside, processor_Inside_Oustside, img, prompt_Inside_Outside, image_transform, device)]
                if curr_predict_inside_outside=="Inside the apartment":
                    curr_imgs_inside.append(img)
            #Прогон модели по всем изображениям и подсчет ответов
            count_verdicts={"No renovation":0,"Old renovation":0,"Designer renovation":0}
            for img in curr_imgs_inside:
                curr_predict_renovations=class_names_renovations[predict_vilt(model_renovations, processor_renovations, img, prompt_renovations, image_transform, device)]
                count_verdicts[curr_predict_renovations]+=1
            #Поиск самого частого ответа модели
            mx=0
            ans_key=0
            for key,cnt in count_verdicts.items():
                if cnt>=mx:
                    mx=cnt
                    ans_key=key
            if ans_key=="No renovation":
                renovations_verdicts.append("Без ремонта")
            elif ans_key=="Old renovation":
                renovations_verdicts.append("Советский ремонт")
            else:
                renovations_verdicts.append("Дизайнерский ремонт")
            
    else:
        renovations_verdicts.append("Не удалось открыть страницу")
print()
print("Загрузка результатов в таблицу all.xlsx")
excel['Ремонт']=renovations_verdicts
file_name = "C:/Parser_Task/Final_thing/FinalWholeProject/result/all.xlsx"

# Удаляем файл, если он существует
if os.path.exists(file_name):
    os.remove(file_name)

# Сохраняем DataFrame в новый Excel-файл
excel.to_excel(file_name, index=False)

print('Работа скрипта завершена')




# # Путь к изображению и текстовый запрос
# image_path = "image_12.jpg"
# prompt = "Classify this apartment image as one of the following categories: Designer renovation, Old renovation, or No renovation."

# # Получаем предсказание
# predicted_class = predict_vilt(model, processor, image_path, prompt, image_transform, device)


