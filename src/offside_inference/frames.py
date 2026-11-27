"""Reading frames from a video or a folder of images."""
import os
import re

import cv2

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")


class MediaSource:
    """Random access to any frame of a video, an image, several images or a folder.

    Frames are requested by index (0..count-1); number(i) is the number shown to the user: the
    position in the video, or the number in the file name if every image has one (000001.jpg...).
    """

    def __init__(self, paths, fps=None):
        paths = [paths] if isinstance(paths, str) else list(paths)
        # Name for the results: folder plus its parent folder (SNMOT-134_img1), or file without extension
        first = os.path.normpath(paths[0])
        if os.path.isdir(first):
            name = f"{os.path.basename(os.path.dirname(first))}_{os.path.basename(first)}"
        elif len(paths) > 1:
            name = os.path.basename(os.path.dirname(first))
        else:
            name = os.path.splitext(os.path.basename(first))[0]
        if len(paths) == 1 and os.path.isdir(paths[0]):
            folder = paths[0]
            paths = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith(IMAGE_EXTENSIONS)]
            if not paths:
                raise ValueError(f"No hay imágenes en {folder}")
        self.video = None
        if len(paths) == 1 and not paths[0].lower().endswith(IMAGE_EXTENSIONS):
            self.video = cv2.VideoCapture(paths[0])
            if not self.video.isOpened():
                raise ValueError(f"No se puede abrir el vídeo {paths[0]}")
            self.kind = "video"
            self.count = int(self.video.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = fps or self.video.get(cv2.CAP_PROP_FPS) or 25.0
            self.size = (int(self.video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.video.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            self.files, self.numbers = None, list(range(self.count))
            self._next = 0
        else:
            missing = [p for p in paths if not os.path.isfile(p)]
            if missing:
                raise ValueError(f"No existe {missing[0]}")
            self.kind = "image" if len(paths) == 1 else "images"
            self.files = sorted(paths) if len(paths) > 1 else paths
            stems = [os.path.splitext(os.path.basename(p))[0] for p in self.files]
            numeric = all(re.fullmatch(r"\d+", s) for s in stems)
            self.numbers = [int(s) for s in stems] if numeric else list(range(len(self.files)))
            self.count = len(self.files)
            self.fps = fps or 25.0
            first = cv2.imread(self.files[0])
            if first is None:
                raise ValueError(f"No se puede leer la imagen {self.files[0]}")
            self.size = (first.shape[1], first.shape[0])
        self.name = name
        self.path = paths[0]

    def number(self, index):
        return self.numbers[index]

    def read(self, index):
        if not 0 <= index < self.count:
            raise IndexError(f"El fotograma {index} está fuera del rango 0-{self.count - 1}")
        if self.files is not None:
            image = cv2.imread(self.files[index])
            if image is None:
                raise ValueError(f"No se puede leer la imagen {self.files[index]}")
            return image
        # Reading forward is exact and fast; for jumps, use the codec's seek
        if index != self._next:
            self.video.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, image = self.video.read()
        if not ok:
            raise ValueError(f"No se puede leer el fotograma {index} del vídeo")
        self._next = index + 1
        return image


class FrameSource:
    """Iterates (frame number, BGR image).

    In a video the number is the position (from 0). In a folder of images, if every name is a number
    (000001.jpg...) that number is used; otherwise the position in alphabetical order.
    """

    def __init__(self, path, start=None, end=None, fps=None):
        self.path = path
        self.start, self.end = start, end
        if os.path.isdir(path):
            files = sorted(f for f in os.listdir(path) if f.lower().endswith(IMAGE_EXTENSIONS))
            if not files:
                raise ValueError(f"No hay imágenes en {path}")
            numeric = all(re.fullmatch(r"\d+", os.path.splitext(f)[0]) for f in files)
            self.items = [(int(os.path.splitext(f)[0]) if numeric else i, os.path.join(path, f))
                          for i, f in enumerate(files)]
            self.fps = fps or 25.0
            first = cv2.imread(self.items[0][1])
            self.size = (first.shape[1], first.shape[0])
            self.video = None
        else:
            self.video = cv2.VideoCapture(path)
            if not self.video.isOpened():
                raise ValueError(f"No se puede abrir el vídeo {path}")
            self.fps = fps or self.video.get(cv2.CAP_PROP_FPS) or 25.0
            self.size = (int(self.video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.video.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            self.items = None

    def _wanted(self, number):
        return (self.start is None or number >= self.start) and (self.end is None or number <= self.end)

    def __iter__(self):
        if self.items is not None:
            for number, path in self.items:
                if self._wanted(number):
                    yield number, cv2.imread(path)
            return
        self.video.set(cv2.CAP_PROP_POS_FRAMES, self.start or 0)
        number = self.start or 0
        while True:
            ok, frame = self.video.read()
            if not ok or (self.end is not None and number > self.end):
                break
            yield number, frame
            number += 1
