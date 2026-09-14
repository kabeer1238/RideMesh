# Third-party notices

## Silero VAD

RideMesh Android vc41 can optionally use the Silero voice activity detection model.
Silero VAD is Copyright (c) 2020-present Silero Team and licensed under the MIT License:
https://github.com/snakers4/silero-vad

## android-vad Silero wrapper

The Android integration uses `com.github.gkonovalov.android-vad:silero:2.0.10`.
Copyright (c) 2019-2025 Georgiy Konovalov, licensed under the MIT License:
https://github.com/gkonovalov/android-vad

The optional detector executes locally on the Android device. RideMesh does not send microphone
audio to an AI service. The original detector remains available when Silero is disabled or cannot initialize.
