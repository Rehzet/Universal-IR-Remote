import threading
import time
import os
import json
import piir
import RPi.GPIO as GPIO
from queue import Queue, Empty
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306


ac_icon = [(2, 4), (3, 4), (4, 4), (5, 4), (6, 4), (7, 4), (8, 4), (9, 4), (10, 4), (11, 4), (12, 4), (13, 4), (14, 4), (15, 4), (16, 4), (17, 4), (2, 5), (3, 5), (4, 5), (5, 5), (6, 5), (7, 5), (8, 5), (9, 5), (10, 5), (11, 5), (12, 5), (13, 5), (14, 5), (15, 5), (16, 5), (17, 5), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6), (7, 6), (8, 6), (9, 6), (10, 6), (11, 6), (12, 6), (13, 6), (14, 6), (15, 6), (16, 6), (17, 6), (2, 7), (3, 7), (4, 7), (5, 7), (6, 7), (7, 7), (8, 7), (9, 7), (10, 7), (11, 7), (12, 7), (13, 7), (14, 7), (15, 7), (16, 7), (17, 7), (2, 8), (3, 8), (4, 8), (5, 8), (6, 8), (7, 8), (8, 8), (9, 8), (10, 8), (11, 8), (12, 8), (13, 8), (14, 8), (15, 8), (16, 8), (17, 8), (2, 9), (3, 9), (4, 9), (5, 9), (6, 9), (7, 9), (8, 9), (9, 9), (10, 9), (11, 9), (12, 9), (13, 9), (14, 9), (15, 9), (16, 9), (17, 9), (2, 10), (3, 10), (4, 10), (5, 10), (6, 10), (7, 10), (8, 10), (9, 10), (10, 10), (11, 10), (12, 10), (13, 10), (14, 10), (15, 10), (16, 10), (17, 10), (2, 11), (3, 11), (4, 11), (15, 11), (16, 11), (17, 11), (3, 12), (4, 12), (15, 12), (16, 12), (5, 13), (6, 13), (9, 13), (10, 13), (13, 13), (14, 13), (5, 14), (6, 14), (9, 14), (10, 14), (13, 14), (14, 14), (5, 15), (6, 15), (9, 15), (10, 15), (13, 15), (14, 15), (4, 16), (5, 16), (9, 16), (10, 16), (14, 16), (15, 16), (9, 17), (10, 17)]



# Configuración de pines GPIO
GPIO_IR_EMITTER = 22
GPIO_BTN_LEFT = 27
GPIO_BTN_RIGHT = 23
GPIO_BTN_SEND = 24

class IRRemoteController:
    def __init__(self, config_path, font_path):
        self.load_config(config_path)
        self.load_icons()
        self.remote = piir.Remote(self.config, GPIO_IR_EMITTER)
        self.index = 0
        self.main_font = ImageFont.truetype(font_path, size=25)
        self.bar_font = ImageFont.truetype(font_path, size=12)
        self.screen_timeout = 10  # Tiempo en segundos para apagar la pantalla
        self.last_interaction_time = time.time()
        self.button_queue = Queue()
        self.display_on = True
        self.setup_gpio()
        self.setup_display()
        self.update_display()

    def load_config(self, path):
        with open(path, 'r') as file:
            self.config = json.load(file)
        self.keys_list = list(self.config['keys'].items())

    def load_icons(self):
        try:
            with open('icons.json', 'r') as file:
                icons = json.load(file)
                
                # Convertimos los valores de cada clave a tuplas
                self.icons_config = {}
                for icon_name, pixels in icons.items():
                    self.icons_config[icon_name] = [tuple(pixel) for pixel in pixels]
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error al leer o parsear el archivo icons.json: {e}")
            self.icons_config = {}

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GPIO_BTN_LEFT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(GPIO_BTN_RIGHT, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(GPIO_BTN_SEND, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        # Configuración de interrupciones GPIO
        GPIO.add_event_detect(GPIO_BTN_LEFT, GPIO.RISING, callback=self.button_callback, bouncetime=200)
        GPIO.add_event_detect(GPIO_BTN_RIGHT, GPIO.RISING, callback=self.button_callback, bouncetime=200)
        GPIO.add_event_detect(GPIO_BTN_SEND, GPIO.RISING, callback=self.button_callback, bouncetime=200)

    def setup_display(self):
        serial = i2c(port=1, address=0x3C)
        self.device = ssd1306(serial, rotate=0)
        self.device.contrast(50)

    def button_callback(self, channel):
        if channel == GPIO_BTN_LEFT:
            self.button_queue.put('left')
        elif channel == GPIO_BTN_RIGHT:
            self.button_queue.put('right')
        elif channel == GPIO_BTN_SEND:
            self.button_queue.put('send')

    def send_data(self, key):
        self.remote.send(key)

    def get_text_center(self, text):
        # Crear una imagen temporal para calcular el tamaño del texto
        dummy_image = Image.new('1', (0, 0))
        dummy_draw = ImageDraw.Draw(dummy_image)
        bbox = dummy_draw.textbbox((0, 0), text, font=self.main_font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x_offset = 0
        y_offset = 0
        x_position = (self.device.width - text_width) // 2 - x_offset
        y_position = (self.device.height - text_height) // 2 - y_offset
        return x_position, y_position

    def get_config_icon(self, type):
        return self.icons_config.get(type, self.icons_config.get('default', []))

    def update_display(self):
        # Crear una imagen en memoria para dibujar
        image = Image.new('1', (self.device.width, self.device.height))
        draw = ImageDraw.Draw(image)

        # Barra superior
        draw.point(self.get_config_icon(self.config['metadata']['type']), fill="white") # Icono del aparato actual. 20px de ancho
        draw.text((23, 0), self.config['metadata']['name'], fill="white", font=self.bar_font)
        

        # Texto de instrucciones
        text = str.upper(self.keys_list[self.index][0])
        x, y = self.get_text_center(text)
        draw.text((x, y), text, fill="white", font=self.main_font)
        

        # Enviar la imagen al dispositivo en una sola operación
        self.device.display(image)

        # Mostrar el dispositivo si está oculto
        if not self.display_on:
            self.device.show()
            self.display_on = True

    def run(self):
        try:
            while True:
                try:
                    # Intentar obtener un evento de botón de la cola
                    event = self.button_queue.get(timeout=0.1)
                    self.last_interaction_time = time.time()

                    if event == 'left':
                        if self.display_on:
                            self.index = (self.index + 1) % len(self.keys_list)
                        self.update_display()
                    elif event == 'right':
                        if self.display_on:
                            self.index = (self.index - 1) % len(self.keys_list)
                        self.update_display()
                    elif event == 'send':
                        current_key, _ = self.keys_list[self.index]
                        self.send_data(current_key)
                        self.update_display()
                except Empty:
                    pass  # No hay eventos, continuar

                # Gestión del tiempo de espera de la pantalla
                elapsed_time = time.time() - self.last_interaction_time
                if elapsed_time >= self.screen_timeout:
                    if self.display_on:
                        self.device.hide()
                        self.display_on = False
                else:
                    if not self.display_on:
                        self.device.show()
                        self.update_display()
                        self.display_on = True

        except KeyboardInterrupt:
            pass
        finally:
            GPIO.cleanup()

if __name__ == "__main__":
    script_dir = os.path.dirname(__file__)
    font_path = os.path.join(script_dir, '../fonts/OpenSans-Regular.ttf')
    config_path = "/home/pi/MandoIR/FUJITSU_AR-RCH1E.json"

    ir_controller = IRRemoteController(config_path, font_path)
    ir_controller.run()
