# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
# import time

# browser = webdriver.Chrome()
# browser.get("https://tu_empresa.woffu.com/")

# # Inicio de sesión
# usuario = browser.find_element(By.ID, "username")
# password = browser.find_element(By.ID, "password")

# usuario.send_keys("tu_usuario")
# password.send_keys("tu_contraseña", Keys.ENTER)

# time.sleep(5)  # espera que cargue la página

# # Automáticamente hacer clic en botón de fichaje (entrada/salida)
# boton_fichar = browser.find_element(By.CSS_SELECTOR, "selector_del_boton_fichaje")
# boton_fichar.click()

# # cerrar navegador
# browser.quit()
