"""Pinned author APIs for text detection and box-prompted segmentation.

Importing this module does not load ML libraries. All inference is local; this
adapter neither downloads nor selects models, frames, or object instances.
"""


class ModelInference:
    def __init__(self, models, device):
        import importlib.metadata
        import json

        distribution = importlib.metadata.distribution('SAM-2')
        source = json.loads(distribution.read_text('direct_url.json') or '{}')
        source_hash = source.get('archive_info', {}).get('hashes', {}).get('sha256')
        expected_source_hash = models['pins']['sam2']['source_archive']['sha256']
        if source_hash != expected_source_hash:
            raise ValueError('Installed SAM-2 source archive differs from the pinned model recipe; '
                             'use bootstrap_auto_masks.sh')
        import torch
        import torchvision
        import transformers
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        expected = {'torch': '2.5.1', 'torchvision': '0.20.1', 'transformers': '4.51.3'}
        actual = {'torch': torch.__version__, 'torchvision': torchvision.__version__,
                  'transformers': transformers.__version__}
        for name, version in expected.items():
            if actual[name].split('+')[0] != version:
                raise ValueError(f'{name} must be {version}, got {actual[name]}')
        self.torch, self.device = torch, device
        if device.startswith('cuda'):
            if not torch.cuda.is_available():
                raise ValueError('CUDA was selected but torch.cuda.is_available() is false')
            torch.cuda.reset_peak_memory_stats(device)
        self.processor = AutoProcessor.from_pretrained(
            str(models['grounding_dino_directory']), local_files_only=True)
        self.detector = AutoModelForZeroShotObjectDetection.from_pretrained(
            str(models['grounding_dino_directory']), local_files_only=True,
            use_safetensors=True, disable_custom_kernels=True).to(device).eval()
        sam = build_sam2(models['sam2_config'], str(models['sam2_checkpoint']),
                         device=device, apply_postprocessing=True)
        self.predictor = SAM2ImagePredictor(sam, mask_threshold=0.0,
                                           max_hole_area=0.0, max_sprinkle_area=0.0)
        self.runtime = {**actual, 'sam2': distribution.version,
                        'sam2_source_archive_sha256': source_hash,
                        'torch_cuda': torch.version.cuda, 'device': device,
                        'detector_custom_kernels': False,
                        'sam2_cuda_extension': False,
                        'sam2_max_hole_area': 0, 'sam2_max_sprinkle_area': 0,
                        'sam2_dynamic_multimask_stability': True,
                        'precision': 'float32; no autocast or TF32 override',
                        'gpu': torch.cuda.get_device_name(device) if device.startswith('cuda') else None}

    def detect(self, image, prompt, box_threshold, text_threshold):
        import math

        inputs = self.processor(images=image, text=prompt, return_tensors='pt').to(self.device)
        with self.torch.inference_mode():
            outputs = self.detector(**inputs)
        result = self.processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=box_threshold,
            text_threshold=text_threshold, target_sizes=[(image.height, image.width)])[0]
        candidates = [{'box_xyxy': box, 'score': score, 'text': text}
                      for box, score, text in zip(result['boxes'].cpu().tolist(),
                                                 result['scores'].cpu().tolist(), result['text_labels'])]
        if any(not all(math.isfinite(v) for v in [*item['box_xyxy'], item['score']])
               for item in candidates):
            raise ValueError('DINO returned nonfinite boxes/scores; no valid candidates declared')
        return candidates

    def segment(self, image, candidates):
        import math
        import numpy as np
        from PIL import Image

        with self.torch.inference_mode():
            self.predictor.set_image(image)
            masks, scores, _ = self.predictor.predict(
                point_coords=None, point_labels=None,
                box=np.asarray([candidate['box_xyxy'] for candidate in candidates], dtype=np.float32),
                multimask_output=False)
        # Native SAM2 returns C,H,W for one box and B,C,H,W for several boxes.
        if masks.ndim == 3:
            masks = masks[None, ...]
        if masks.shape != (len(candidates), 1, image.height, image.width):
            raise ValueError(f'SAM2 did not return source-sized masks: {masks.shape}')
        if not np.isfinite(masks).all() or not all(math.isfinite(float(score)) for score in scores.reshape(-1)):
            raise ValueError('SAM2 returned nonfinite masks/scores; no valid mask declared')
        return [(Image.fromarray((mask[0] > 0).astype('uint8') * 255), float(score.reshape(-1)[0]))
                for mask, score in zip(masks, scores)]

    def memory(self):
        if not self.device.startswith('cuda'):
            return {'cuda_peak_allocated_bytes': None, 'cuda_peak_reserved_bytes': None}
        self.torch.cuda.synchronize(self.device)
        return {'cuda_peak_allocated_bytes': self.torch.cuda.max_memory_allocated(self.device),
                'cuda_peak_reserved_bytes': self.torch.cuda.max_memory_reserved(self.device)}
