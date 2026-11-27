/**
 * Turning any photo into the homepage banner's 1920 x 800.
 *
 * Done here, in the browser, so a 6 MB phone photo goes up as a ~300 KB JPEG
 * that is exactly the size the website shows. Re-drawing it on a canvas also
 * drops the photo's EXIF data, the GPS position a phone camera records
 * included, before it ever leaves the office computer.
 */

export const BANNER_WIDTH = 1920;
export const BANNER_HEIGHT = 800;
/** Below this, the photo is being stretched and will look soft on a big screen. */
export const SHARP_ENOUGH_WIDTH = 1400;

export interface SourcePhoto {
  bitmap: ImageBitmap;
  width: number;
  height: number;
}

export const readPhoto = async (file: File): Promise<SourcePhoto> => {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
    throw new Error("Please choose a JPEG, PNG or WebP photo.");
  }
  // Honour the camera's rotation, so a portrait phone photo is not sideways.
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  return { bitmap, width: bitmap.width, height: bitmap.height };
};

/**
 * Crop to the banner's shape and resize. `focusX` and `focusY` (0 to 1) say
 * which part of the photo to keep when it is cut: 0.5 is the middle, 0 the
 * left or top edge.
 */
export const cropForBanner = (photo: SourcePhoto, focusX: number, focusY: number): Promise<Blob> => {
  const scale = Math.max(BANNER_WIDTH / photo.width, BANNER_HEIGHT / photo.height);
  const sw = BANNER_WIDTH / scale;
  const sh = BANNER_HEIGHT / scale;
  const sx = (photo.width - sw) * focusX;
  const sy = (photo.height - sh) * focusY;

  const canvas = document.createElement("canvas");
  canvas.width = BANNER_WIDTH;
  canvas.height = BANNER_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("This browser cannot prepare the photo."));
  context.imageSmoothingQuality = "high";
  context.drawImage(photo.bitmap, sx, sy, sw, sh, 0, 0, BANNER_WIDTH, BANNER_HEIGHT);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("The photo could not be prepared."))),
      "image/jpeg",
      0.85,
    );
  });
};
