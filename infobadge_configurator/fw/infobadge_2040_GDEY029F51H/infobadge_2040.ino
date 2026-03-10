#include <GxEPD2_BW.h>
#include <GxEPD2_3C.h>
#include <GxEPD2_4C.h>
#include <GxEPD2_7C.h>
#include <Adafruit_GFX.h>
#include <Fonts/FreeSansBold12pt7b.h> 
#include <Fonts/FreeSans9pt7b.h> 
#include "fonts/Quantico_Regular7pt7b.h"
#include "fonts/Quantico_Bold7pt7b.h"
#include "fonts/Quantico_Bold12pt7b.h"
#include <qrcode.h>

#define SPI_MISO 20
#define SPI_MOSI 19
#define SPI_SCK 18

#define LED1_PIN 28
#define LED2_PIN 27

#define PB1_PIN 29
#define PB2_PIN 26

#define RECT_OFFSET 5

QRCode qrcode;

uint8_t qrcodeData[108];  // Versión 3 (29x29)
int reset_display;

// Define el modelo de tu display ePaper
GxEPD2_4C<GxEPD2_290c_GDEY029F51H, GxEPD2_290c_GDEY029F51H::HEIGHT> display(GxEPD2_290c_GDEY029F51H(/*CS*/ 16, /*DC*/ 14, /*RST*/ 13, /*BUSY*/ 12));

void drawQRCode(String url) {
  qrcode_initText(&qrcode, qrcodeData, 3, ECC_LOW, url.c_str());

  int size = qrcode.size;
  int scale = 3;

  int xOffset = 200;
  int yOffset = 20;

  for (int y = 0; y < size; y++) {
    for (int x = 0; x < size; x++) {
      if (qrcode_getModule(&qrcode, x, y)) {
        display.fillRect(xOffset + x * scale, yOffset + y * scale, scale, scale, GxEPD_RED);
      }
    }
  }
}


void setup() {

  delay(2000);

  Serial.begin(115200);
  // while(!Serial);

  while (Serial.available()) Serial.read();  // vacía el buffer

  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);
  pinMode(PB1_PIN, INPUT);
  pinMode(PB2_PIN, INPUT);

  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);
  
  MbedSPI SPI(SPI_MISO,SPI_MOSI,SPI_SCK);
  
  if (digitalRead(PB1_PIN))
    reset_display = 1;
  else 
    reset_display = 0;
}

void loop() {
  static String receivedStrings[5];
  static int count = 0;
  int restart = 0;

  /* text bounds */
  int16_t x1, y1;
  uint16_t w, h;

  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.length() > 0) {
      receivedStrings[count] = input;
      count++;

      digitalWrite(LED1_PIN, HIGH);
      Serial.println(receivedStrings[count - 1]);
    }
  }

  if (reset_display){
    receivedStrings[0] = "InfoBadge2040";
    receivedStrings[1] = "Scan QR";
    receivedStrings[2] = "to customize";
    receivedStrings[3] = "@TheBadg.ES";
    receivedStrings[4] = "https://github.com/thebadg-es/infobadge2040";
  }

  if (count == 5 || restart || reset_display) {

    digitalWrite(LED2_PIN, HIGH);

    display.init(115200, true, 10, false, SPI, SPISettings(4000000, MSBFIRST, SPI_MODE0)); // Inicializa el display
    delay(1000);
    display.setRotation(3); // Ajusta la orientación si es necesario

    display.getTextBounds(receivedStrings[3], 10, 110, &x1, &y1, &w, &h);

    // Hacemos una escritura vacía solo para inicializar correctamente
    display.setTextColor(GxEPD_BLACK);
    display.setFont(&FreeSansBold12pt7b);

    display.firstPage();

    unsigned long start = millis();

    do {
      display.fillScreen(GxEPD_WHITE);  // <-- debe estar dentro del bucle
      display.setFont(&Quantico_Bold12pt7b);
      display.setCursor(10, 30);
      display.print(receivedStrings[0]);
      display.setTextColor(GxEPD_BLACK);
      display.setFont(&Quantico_Bold7pt7b);
      display.setCursor(10, 60);
      display.print(receivedStrings[1]);
      display.setCursor(10, 85);
      display.print(receivedStrings[2]);

      display.fillRect(x1-RECT_OFFSET, y1-RECT_OFFSET, w+4+RECT_OFFSET, h+2+RECT_OFFSET, GxEPD_BLACK);

      display.setTextColor(GxEPD_YELLOW);
      display.setCursor(10, 110);
      display.print(receivedStrings[3]);

      drawQRCode(receivedStrings[4]);

    } while (display.nextPage());

    unsigned long duration = millis() - start;

    // Check duration
    if (duration > 5000) {
      // Reinicia para recibir nuevas strings
      count = 0;
      digitalWrite(LED1_PIN, LOW);
      digitalWrite(LED2_PIN, LOW);
      restart = 0;
      reset_display = 0;
    }
    else {
      delay(1000);
      // Serial.println("Retrying...");
      restart = 1;
    }
  }
}
