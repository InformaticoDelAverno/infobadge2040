#include <GxEPD2_BW.h>
#include <GxEPD2_3C.h>
#include <GxEPD2_4C.h>
#include <GxEPD2_7C.h>
#include <Adafruit_GFX.h>
#include "GxEPD2_290c_GDEY029F52.h"

#define SPI_MISO 20
#define SPI_MOSI 19
#define SPI_SCK 18

#define LED1_PIN 28
#define LED2_PIN 27

// Panel used by this editor firmware (GoodDisplay GDEY029F52 local driver). Native: 128x296.
GxEPD2_4C<GxEPD2_290c_GDEY029F52, GxEPD2_290c_GDEY029F52::HEIGHT> display(
  GxEPD2_290c_GDEY029F52(/*CS*/ 16, /*DC*/ 14, /*RST*/ 13, /*BUSY*/ 12)
);
MbedSPI badgeSPI(SPI_MISO, SPI_MOSI, SPI_SCK);

// Fixed logical orientation expected by infobadge_editor.py.
static const uint16_t LOGICAL_W = 296;
static const uint16_t LOGICAL_H = 128;
// Physical size for GDEY029F52 with rotation(3): 296x128.
static const uint16_t PHYS_W = 296;
static const uint16_t PHYS_H = 128;

static const uint32_t SERIAL_TIMEOUT_MS = 10000;
static const uint32_t MAX_PACKED_BYTES = (LOGICAL_W * LOGICAL_H + 3UL) / 4UL;
static uint8_t frameBuffer[MAX_PACKED_BYTES];

struct __attribute__((packed)) FrameHeader {
  char magic[4];
  uint16_t width;
  uint16_t height;
  uint8_t format;
  uint32_t dataLen;
};
static_assert(sizeof(FrameHeader) == 13, "FrameHeader size must be 13 bytes");

bool readExact(uint8_t* dst, size_t len) {
  size_t readCount = 0;
  unsigned long t0 = millis();

  while (readCount < len) {
    if (Serial.available()) {
      dst[readCount++] = (uint8_t)Serial.read();
      t0 = millis();
    } else if (millis() - t0 > SERIAL_TIMEOUT_MS) {
      return false;
    }
  }
  return true;
}

bool discardExact(size_t len) {
  unsigned long t0 = millis();
  while (len > 0) {
    if (Serial.available()) {
      (void)Serial.read();
      len--;
      t0 = millis();
    } else if (millis() - t0 > SERIAL_TIMEOUT_MS) {
      return false;
    }
  }
  return true;
}

void drainAvailable() {
  while (Serial.available()) {
    (void)Serial.read();
  }
}

uint16_t colorFromIndex(uint8_t idx) {
  switch (idx & 0x03) {
    case 0: return GxEPD_WHITE;
    case 1: return GxEPD_BLACK;
    case 2: return GxEPD_RED;
    case 3: return GxEPD_YELLOW;
    default: return GxEPD_WHITE;
  }
}

uint8_t unpack2bppPixel(const uint8_t* data, uint16_t w, uint16_t x, uint16_t y) {
  uint32_t i = (uint32_t)y * (uint32_t)w + (uint32_t)x;
  uint8_t packed = data[i >> 2];
  uint8_t shift = (3 - (i & 0x03)) * 2;
  return (packed >> shift) & 0x03;
}

void renderPacked2bpp(const uint8_t* data, uint16_t w, uint16_t h) {
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);

    // Logical editor frame now matches panel size (296x128).
    for (uint16_t y = 0; y < PHYS_H; y++) {
      uint16_t srcY = ((uint32_t)y * h) / PHYS_H;
      if (srcY >= h) srcY = h - 1;
      for (uint16_t x = 0; x < PHYS_W; x++) {
        uint16_t srcX = ((uint32_t)x * w) / PHYS_W;
        if (srcX >= w) srcX = w - 1;
        uint8_t idx = unpack2bppPixel(data, w, srcX, srcY);
        display.drawPixel(x, y, colorFromIndex(idx));
      }
    }
  } while (display.nextPage());
}

void renderTestPattern() {
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);

    // Four color blocks to verify color mapping and orientation.
    display.fillRect(0, 0, PHYS_W / 2, PHYS_H / 2, GxEPD_WHITE);
    display.fillRect(PHYS_W / 2, 0, PHYS_W / 2, PHYS_H / 2, GxEPD_BLACK);
    display.fillRect(0, PHYS_H / 2, PHYS_W / 2, PHYS_H / 2, GxEPD_RED);
    display.fillRect(PHYS_W / 2, PHYS_H / 2, PHYS_W / 2, PHYS_H / 2, GxEPD_YELLOW);

    // Cross lines for orientation check.
    display.drawLine(0, 0, PHYS_W - 1, PHYS_H - 1, GxEPD_BLACK);
    display.drawLine(0, PHYS_H - 1, PHYS_W - 1, 0, GxEPD_BLACK);
  } while (display.nextPage());
}

void initDisplayLikeOfficial() {
  // Intentionally same style as original fw: init on every draw cycle.
  display.init(115200, true, 10, false, badgeSPI, SPISettings(4000000, MSBFIRST, SPI_MODE0));
  delay(1000);
  display.setRotation(3);
}

void setup() {
  delay(2000);

  Serial.begin(115200);
  while (Serial.available()) Serial.read();

  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);

  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);

  Serial.println("IBF1_READY");
  Serial.print("SIZE ");
  Serial.print(LOGICAL_W);
  Serial.print(' ');
  Serial.println(LOGICAL_H);
}

void loop() {
  if (Serial.available() > 0 && (Serial.peek() == 'S' || Serial.peek() == 'T')) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "SIZE?") {
      Serial.print("SIZE ");
      Serial.print(LOGICAL_W);
      Serial.print(' ');
      Serial.println(LOGICAL_H);
    } else if (cmd == "TEST") {
      digitalWrite(LED2_PIN, HIGH);
      initDisplayLikeOfficial();
      renderTestPattern();
      digitalWrite(LED2_PIN, LOW);
      Serial.println("OK_TEST");
    } else {
      Serial.println("ERR_CMD");
    }
    return;
  }

  if (Serial.available() < (int)sizeof(FrameHeader)) {
    delay(10);
    return;
  }

  FrameHeader hdr;
  if (!readExact((uint8_t*)&hdr, sizeof(FrameHeader))) {
    Serial.println("ERR_TIMEOUT_HEADER");
    return;
  }

  if (memcmp(hdr.magic, "IBF1", 4) != 0) {
    Serial.println("ERR_MAGIC");
    return;
  }

  if (hdr.format != 0) {
    if (hdr.dataLen > 0 && hdr.dataLen <= MAX_PACKED_BYTES) {
      (void)discardExact(hdr.dataLen);
    } else {
      drainAvailable();
    }
    Serial.println("ERR_FORMAT");
    return;
  }

  if (hdr.width != LOGICAL_W || hdr.height != LOGICAL_H) {
    if (hdr.dataLen > 0 && hdr.dataLen <= MAX_PACKED_BYTES) {
      (void)discardExact(hdr.dataLen);
    } else {
      drainAvailable();
    }
    Serial.print("SIZE ");
    Serial.print(LOGICAL_W);
    Serial.print(' ');
    Serial.println(LOGICAL_H);
    Serial.println("ERR_SIZE");
    return;
  }

  const uint32_t expectedLen = ((uint32_t)LOGICAL_W * (uint32_t)LOGICAL_H + 3UL) / 4UL;
  if (hdr.dataLen != expectedLen || hdr.dataLen > MAX_PACKED_BYTES) {
    if (hdr.dataLen > 0 && hdr.dataLen <= MAX_PACKED_BYTES) {
      (void)discardExact(hdr.dataLen);
    } else {
      drainAvailable();
    }
    Serial.println("ERR_LEN");
    return;
  }

  digitalWrite(LED1_PIN, HIGH);

  if (!readExact(frameBuffer, hdr.dataLen)) {
    digitalWrite(LED1_PIN, LOW);
    Serial.println("ERR_TIMEOUT_DATA");
    return;
  }

  digitalWrite(LED2_PIN, HIGH);
  initDisplayLikeOfficial();
  renderPacked2bpp(frameBuffer, LOGICAL_W, LOGICAL_H);
  digitalWrite(LED2_PIN, LOW);
  digitalWrite(LED1_PIN, LOW);

  Serial.println("OK");
}
