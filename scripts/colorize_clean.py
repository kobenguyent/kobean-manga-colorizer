import sys
import os
import cv2
import torch
import numpy as np
from PIL import Image
from torchvision.transforms import ToTensor
from networks.models import Colorizer
from colorizer_engine import resize_pad_manga

def main():
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    model = Colorizer().to(device)
    weights = torch.load('networks/generator.zip', map_location=device)
    model.generator.load_state_dict(weights)
    model.eval()

    img_path = 'sessions/189014cc-95c1-4ed6-890b-22b2d5e1e955/original/page_0061.jpg'
    orig_pil = Image.open(img_path).convert('RGB')
    orig_np = np.array(orig_pil).astype(np.float32) / 255.0
    h_orig, w_orig = orig_np.shape[:2]

    # Inference at 768px
    img_pad, pad = resize_pad_manga(orig_np, size=768)
    tens_in = ToTensor()(img_pad).unsqueeze(0).to(device)
    hint = torch.zeros(1, 4, tens_in.shape[2], tens_in.shape[3], dtype=torch.float32, device=device)

    with torch.no_grad():
        fake_color, _ = model(torch.cat([tens_in, hint], 1))
        fake_color = fake_color.detach()

    result_rn = fake_color[0].detach().cpu().permute(1, 2, 0) * 0.5 + 0.5
    if pad[0] != 0:
        result_rn = result_rn[:-pad[0]]
    if pad[1] != 0:
        result_rn = result_rn[:, :-pad[1]]

    rn_np = np.clip(result_rn.numpy(), 0.0, 1.0)
    rn_rgb = (rn_np * 255.0).astype(np.uint8)

    # Upscale
    color_upscaled_rgb = cv2.resize(rn_rgb, (w_orig, h_orig), interpolation=cv2.INTER_LANCZOS4)
    orig_rgb = (orig_np * 255.0).astype(np.uint8)
    gray_orig = cv2.cvtColor(orig_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0

    color_hsv = cv2.cvtColor(color_upscaled_rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = color_hsv[:, :, 1]
    val = color_hsv[:, :, 2]

    # Clean background paper for borderless/splash pages
    paper_mask = (gray_orig >= 0.96) & (sat < 28.0) & (val >= 235.0)

    # Native line art multiply blending
    ink_threshold = 0.30
    line_multiplier = np.clip((gray_orig - 0.04) / ink_threshold, 0.0, 1.0)
    sat_boost = np.clip((sat - 25.0) / 160.0, 0.0, 1.0)
    ink_floor = 0.12 * sat_boost
    effective_mult = np.maximum(line_multiplier, ink_floor)

    final_rgb = np.clip(
        color_upscaled_rgb.astype(np.float32) * effective_mult[:, :, np.newaxis], 0, 255
    ).astype(np.uint8)

    final_rgb[paper_mask] = 255

    out_path = '/Users/kobet/Desktop/mbp_refined.png'
    cv2.imwrite(out_path, cv2.cvtColor(final_rgb, cv2.COLOR_RGB2BGR))
    print(f'Saved {out_path} successfully!')

if __name__ == '__main__':
    main()
