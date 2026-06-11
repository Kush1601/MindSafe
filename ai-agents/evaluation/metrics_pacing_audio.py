"""
Pacing and audio metrics computation.
Analyzes video cuts, motion, loudness, music, and sound effects.
"""

import numpy as np
import subprocess
import json
import warnings
from typing import List, Dict, Optional
from .video_preprocess import Shot


def compute_pacing_metrics(shots: List[Shot], duration_sec: float) -> Dict[str, float]:
    """
    Compute pacing metrics from shot list.
    
    Args:
        shots: List of Shot objects
        duration_sec: Total video duration in seconds
        
    Returns:
        Dictionary with:
        - cuts_per_minute: Number of cuts per minute
        - avg_shot_length: Average shot duration in seconds
    """
    if not shots or duration_sec <= 0:
        return {
            "cuts_per_minute": 0.0,
            "avg_shot_length": 0.0
        }
    
    num_cuts = len(shots) - 1  # Number of transitions
    duration_min = duration_sec / 60.0
    
    cuts_per_minute = num_cuts / duration_min if duration_min > 0 else 0.0
    
    shot_lengths = [shot.duration for shot in shots]
    avg_shot_length = np.mean(shot_lengths) if shot_lengths else 0.0
    
    return {
        "cuts_per_minute": cuts_per_minute,
        "avg_shot_length": avg_shot_length
    }


def compute_motion_metrics(video_path: str, shots: Optional[List[Shot]] = None, 
                          sample_fps: int = 2) -> Dict[str, float]:
    """
    Compute motion metrics using optical flow.
    This can be computationally expensive for long videos.
    
    Args:
        video_path: Path to video file
        shots: Optional list of shots (not used in basic implementation)
        sample_fps: Frame rate to sample for motion analysis
        
    Returns:
        Dictionary with:
        - motion_mean: Average motion magnitude
        - motion_high_frac: Fraction of frames with high motion
    """
    try:
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Could not open video: {video_path}")
            return {"motion_mean": 0.0, "motion_high_frac": 0.0}
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Calculate frame skip for sampling
        frame_skip = max(1, int(fps / sample_fps))
        
        motion_magnitudes = []
        prev_gray = None
        frame_idx = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Only process every Nth frame
            if frame_idx % frame_skip == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
                
                if prev_gray is not None:
                    # Calculate optical flow using Farneback method
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None,
                        pyr_scale=0.5, levels=3, winsize=15,
                        iterations=3, poly_n=5, poly_sigma=1.2, flags=0
                    )
                    
                    # Calculate magnitude
                    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                    mean_mag = np.mean(mag)
                    motion_magnitudes.append(mean_mag)
                
                prev_gray = gray
            
            frame_idx += 1
        
        cap.release()
        
        if not motion_magnitudes:
            return {"motion_mean": 0.0, "motion_high_frac": 0.0}
        
        motion_mean = np.mean(motion_magnitudes)
        motion_std = np.std(motion_magnitudes)
        
        # Define "high motion" as > mean + 0.5*std
        high_motion_threshold = motion_mean + 0.5 * motion_std
        motion_high_frac = np.mean([m > high_motion_threshold for m in motion_magnitudes])
        
        return {
            "motion_mean": float(motion_mean),
            "motion_high_frac": float(motion_high_frac)
        }
    
    except ImportError:
        print("OpenCV not installed. Install with: pip install opencv-python")
        return {"motion_mean": 0.0, "motion_high_frac": 0.0}
    except Exception as e:
        print(f"Error computing motion metrics: {e}")
        return {"motion_mean": 0.0, "motion_high_frac": 0.0}


def compute_audio_metrics(audio_path: str, duration_sec: Optional[float] = None) -> Dict[str, float]:
    """
    Compute audio metrics using librosa.
    
    Args:
        audio_path: Path to audio file
        duration_sec: Video duration (if None, computed from audio)
        
    Returns:
        Dictionary with:
        - loudness_mean: Mean loudness in dB
        - dynamic_range: Difference between max and min loudness
        - music_ratio: Estimated fraction of time with music
        - sfx_rate: Estimated sound effects per minute
    """
    try:
        import librosa
        import librosa.feature

        # Suppress noisy backend warnings from librosa/audioread for speed runs
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Load audio
            y, sr = librosa.load(audio_path, sr=16000, mono=True)
        
        if duration_sec is None:
            duration_sec = len(y) / sr
        
        # Compute loudness (RMS energy converted to dB)
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        rms_db = librosa.amplitude_to_db(rms, ref=np.max)
        loudness_mean = float(np.mean(rms_db))
        dynamic_range = float(np.max(rms_db) - np.min(rms_db))
        
        # Estimate music vs speech using spectral features
        # Music typically has more harmonic content and regularity
        spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        contrast_mean = np.mean(spectral_contrast, axis=1)
        
        # Chromagram for harmonic content
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        chroma_energy = np.sum(chroma, axis=0)
        
        # Simple heuristic: high chroma energy suggests music
        music_threshold = np.percentile(chroma_energy, 60)
        music_frames = np.sum(chroma_energy > music_threshold)
        total_frames = len(chroma_energy)
        music_ratio = float(music_frames / total_frames) if total_frames > 0 else 0.0
        
        # Detect sound effects as short, transient high-frequency bursts
        # Use onset detection for transients
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            units='frames',
            backtrack=False
        )
        
        # Filter for strong onsets (likely SFX)
        strong_onsets = [f for f in onset_frames if onset_env[f] > np.percentile(onset_env, 85)]
        
        duration_min = duration_sec / 60.0
        sfx_rate = len(strong_onsets) / duration_min if duration_min > 0 else 0.0
        
        return {
            "loudness_mean": loudness_mean,
            "dynamic_range": dynamic_range,
            "music_ratio": music_ratio,
            "sfx_rate": sfx_rate
        }
    
    except ImportError:
        print("Librosa not installed. Install with: pip install librosa")
        return {
            "loudness_mean": -15.0,
            "dynamic_range": 20.0,
            "music_ratio": 0.3,
            "sfx_rate": 2.0
        }
    except Exception as e:
        print(f"Error computing audio metrics: {e}")
        return {
            "loudness_mean": -15.0,
            "dynamic_range": 20.0,
            "music_ratio": 0.3,
            "sfx_rate": 2.0
        }


def compute_pacing_audio_features(video_path: str, audio_path: str, 
                                  shots: List[Shot]) -> Dict[str, float]:
    """
    Compute all pacing and audio features.
    
    Args:
        video_path: Path to video file
        audio_path: Path to audio file
        shots: List of detected shots
        
    Returns:
        Dictionary with all pacing and audio metrics
    """
    # Import get_video_duration from video_preprocess
    from .video_preprocess import get_video_duration
    
    duration_sec = get_video_duration(video_path)
    
    # Compute pacing metrics
    pacing = compute_pacing_metrics(shots, duration_sec)
    
    # Compute motion metrics (can be slow). For speed, we skip motion analysis
    # by default and use neutral defaults.
    compute_motion = False
    if compute_motion:
        motion = compute_motion_metrics(video_path, shots, sample_fps=1)
    else:
        motion = {"motion_mean": 0.0, "motion_high_frac": 0.0}
    
    # Compute audio metrics
    audio = compute_audio_metrics(audio_path, duration_sec)
    
    # Merge all metrics
    return {
        **pacing,
        **motion,
        **audio
    }

