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

# Configuración de pines GPIO
GPIO_IR_EMITTER = 22
GPIO_BTN_LEFT = 27
GPIO_BTN_RIGHT = 23
GPIO_BTN_SEND = 24

class IRRemoteController:
    def __init__(self, config_path, font_path):
        self.load_config(config_path)
        self.remote = piir.Remote(self.config, GPIO_IR_EMITTER)
        self.index = 0
        self.font = ImageFont.truetype(font_path, size=25)
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
        bbox = dummy_draw.textbbox((0, 0), text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x_position = (self.device.width - text_width) // 2
        y_position = (self.device.height - text_height) // 2
        return x_position, y_position

    def update_display(self):
        # Crear una imagen en memoria para dibujar
        image = Image.new('1', (self.device.width, self.device.height))
        draw = ImageDraw.Draw(image)

        text = str.upper(self.keys_list[self.index][0])
        x, y = self.get_text_center(text)
        draw.text((x, y), text, fill="white", font=self.font)

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
    font_path = os.path.join(script_dir, '../fonts/gomarice_no_continue.ttf')
    config_path = "/home/pi/MandoIR/FUJITSU_AR-RCH1E.json"

    ir_controller = IRRemoteController(config_path, font_path)
    ir_controller.run()
