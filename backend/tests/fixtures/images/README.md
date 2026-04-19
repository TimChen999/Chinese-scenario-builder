# Image fixtures

These files are referenced by the live tests in
`backend/tests/live/test_vision_live.py` and the manual verification
in DESIGN.md Step 4. They are committed as **empty placeholders**;
you must replace them with real photos before the live OCR tests
will pass meaningfully.

## What to provide

Five hand-curated, real-world photographs taken by people (not stock
photography, not screenshots, not generated images), chosen to
exercise the OCR + filter modules:

### Good fixtures (should pass the filter and yield clean OCR)

| File | Subject | Selection criteria |
|---|---|---|
| `menu_001.jpg`   | A real menu (restaurant / breakfast stall / drink shop) | At least 6 menu items with prices in 元 / ¥; no English; legible Chinese; phone-camera-style framing. |
| `sign_001.jpg`   | A real public sign (street, shop, station)              | Multi-character Chinese sign; outdoor or interior sign; no overlay graphics. |
| `notice_001.jpg` | A real notice / warning / closing-hours poster          | Multi-line Chinese paragraph (e.g., a building notice, store hours, COVID rules); printed or handwritten OK. |

### Bad fixtures (should be rejected by the quality filter)

| File | Subject | Why it should reject |
|---|---|---|
| `stock_001.jpg`  | A stock-photo-style image of generic Chinese characters or a Photoshopped scene | Not authentic; filter should reject "real photo? no". |
| `blurry_001.jpg` | A real photo that is too blurry / low-res to read | Filter should reject "text legible? no". |

## Expected-OCR JSON files

Each good fixture has a sibling `_expected.json` with the **canonical
OCR output** you would expect Gemini Pro to produce. The live test
asserts character-level Jaccard similarity >= 0.85 between the live
result and the expected `raw_text`.

Format:

```json
{
  "raw_text": "豆浆  3元\n油条  2元\n包子(肉)  4元",
  "scene_type": "menu",
  "notes": "handwritten menu on wall"
}
```

When you swap in real images, hand-edit each `_expected.json` to
match what is actually visible. Set `raw_text` exactly as it appears
on the photo, including spacing and line breaks.

## How to source

Avoid:
- Google Image stock results (they will look wrong)
- AI-generated images (the filter will hopefully catch them)
- Screenshots of textbooks or learning apps (not authentic context)

Good sources:
- Photos from your own travel
- Reddit r/ChineseLanguage, r/learnchinese (with attribution)
- Public-domain image collections (Wikimedia, etc.)
- Friends who travel to / live in China
