import subprocess

# Запускаем приложение
process = subprocess.Popen(['C:\Parser_Task\parser_avito-master\AvitoParserFinal\parser_avito_2_1_0.exe'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Ожидаем завершения приложения
process.wait()

# Выполняем необходимые команды после завершения приложения
print("Приложение завершено. Выполняем дополнительные команды...")
# Здесь ваши команды, которые нужно выполнить после завершения приложения
