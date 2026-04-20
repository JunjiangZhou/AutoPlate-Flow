import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os

def cv2ImgAddText(img, text, left, top, textColor=(0, 255, 0), textSize=20):
    if not text:
        return img
    if left < 0:
        left = 0
    if top < 0:
        top = 0
    try:
        if isinstance(img, np.ndarray):
            img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        else:
            img_pil = img
        draw = ImageDraw.Draw(img_pil)
        font_path = os.path.join(os.path.dirname(__file__), "..", "fonts", "platech.ttf")
        if not os.path.exists(font_path):
            font_path = "fonts/platech.ttf"
        fontText = ImageFont.truetype(font_path, textSize, encoding="utf-8")
        draw.text((left, top), text, fill=textColor, font=fontText)
        return cv2.cvtColor(np.asarray(img_pil), cv2.COLOR_RGB2BGR)
    except Exception as e:
        # 字体加载失败时回退到 cv2.putText（不支持中文）
        if isinstance(img, np.ndarray):
            cv2.putText(img, text, (left, top + textSize), cv2.FONT_HERSHEY_SIMPLEX, 0.6, textColor, 2)
        return img

