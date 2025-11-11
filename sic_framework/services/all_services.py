from sic_framework import SICComponentManager
from sic_framework.services.face_detection_dnn.face_detection_dnn import (
    DNNFaceDetectionComponent,
)
from sic_framework.services.openai_gpt.gpt import GPTComponent
from sic_framework.services.openai_whisper_stt.whisper_stt import (
    WhisperComponent,
)
from sic_framework.services.streaming_sortformer.stm_sortformer import (
    STMSortformerComponent,
)

if __name__ == "__main__":
    SICComponentManager(
        [
            WhisperComponent,
            GPTComponent,
            DNNFaceDetectionComponent,
            STMSortformerComponent,
        ]
    )
