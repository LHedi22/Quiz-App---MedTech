"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { evaluateCaptureQuality } from "@/lib/scan/imageQuality";

type CameraState = "initializing" | "ready" | "permission_denied" | "no_camera" | "error";

/** Browser camera capture screen (Subtask 7c.2). Mirrors mobile's
 * CameraCaptureScreen (Phase 8.2) UX contract - same screen stays up after a
 * failed pre-check, showing an inline retake message rather than navigating
 * away - but submission to `POST /scan` and connectivity gating are wired in
 * by Subtask 7c.3, not here. */
export default function ScanPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [cameraState, setCameraState] = useState<CameraState>("initializing");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [retakeReason, setRetakeReason] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function initCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (!cancelled) setCameraState("no_camera");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setCameraState("ready");
      } catch (err) {
        if (cancelled) return;
        const name = err instanceof DOMException ? err.name : "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") {
          setCameraState("permission_denied");
        } else if (
          name === "NotFoundError" ||
          name === "DevicesNotFoundError" ||
          name === "OverconstrainedError"
        ) {
          setCameraState("no_camera");
        } else {
          setCameraState("error");
          setCameraError(err instanceof Error ? err.message : String(err));
        }
      }
    }

    initCamera();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const capture = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || cameraState !== "ready" || capturing) return;

    setCapturing(true);
    setRetakeReason(null);
    try {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const quality = evaluateCaptureQuality(imageData);
      if (quality.needsRetake) {
        setRetakeReason(
          quality.isBlurry
            ? "Image looks blurry — hold steady and retake."
            : "No page detected in frame — retake.",
        );
        return;
      }
      // Subtask 7c.3 wires the passing frame into POST /scan here.
    } finally {
      setCapturing(false);
    }
  }, [cameraState, capturing]);

  return (
    <div className="flex min-h-[60vh] flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold text-olive-deep">Scan</h1>

      <div
        className="relative flex-1 overflow-hidden rounded-sm border border-sand bg-ink"
        data-testid="camera-preview"
      >
        <video ref={videoRef} autoPlay playsInline muted className="h-full min-h-[50vh] w-full object-cover" />

        {cameraState !== "ready" && (
          <div
            className="absolute inset-0 flex items-center justify-center p-6 text-center text-paper"
            data-testid="camera-status"
          >
            {cameraState === "initializing" && <p>Starting camera…</p>}
            {cameraState === "permission_denied" && (
              <p data-testid="camera-permission-denied">
                Camera access was denied. Allow camera permission in your browser settings to
                scan.
              </p>
            )}
            {cameraState === "no_camera" && (
              <p data-testid="camera-unavailable">No camera available on this device.</p>
            )}
            {cameraState === "error" && (
              <p data-testid="camera-error">Camera unavailable: {cameraError}</p>
            )}
          </div>
        )}

        {retakeReason && (
          <div
            className="absolute inset-x-4 bottom-6 rounded-sm border border-flag/40 bg-flag-soft p-3 text-sm text-flag"
            data-testid="retake-prompt"
          >
            {retakeReason}
          </div>
        )}
      </div>

      <div className="flex justify-center pb-2">
        <button
          type="button"
          data-testid="capture-button"
          aria-label="Capture"
          onClick={capture}
          disabled={cameraState !== "ready" || capturing}
          className="flex h-16 w-16 items-center justify-center rounded-full bg-olive text-2xl text-paper transition-colors hover:bg-olive-deep disabled:opacity-40"
        >
          {capturing ? "…" : "●"}
        </button>
      </div>

      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
}
