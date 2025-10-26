How to use a service
=======================================

The social interaction cloud has many components available for you to speed up creating social interactions with the robots.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 15 15 15

   * - **Service**
     - **Command**
     - **Source**
     - **Demo files**
     - **Install**
     - **Notes**
   * - **Dialogflow** for creating conversational agents using google's framework. This provides a flow chart like dialog management and speech recognition.
     - ``run-dialogflow``
     - `dialogflow <https://github.com/Social-AI-VU/social-interaction-cloud/blob/main/sic_framework/services/dialogflow/dialogflow.py>`_
     - `demo_desktop_microphone_dialogflow.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_microphone_dialogflow.py>`_ or `demo_nao_dialogflow <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/nao/demo_nao_dialogflow.py>`_
     - ``pip install social-interaction-cloud[dialogflow]``
     -  
   * - **Face detection** using OpenCV's cascading classifier, which is very fast and can run on a laptop CPU
     - ``run-face-detection``
     - `face_detection <https://github.com/Social-AI-VU/social-interaction-cloud/blob/main/sic_framework/services/face_detection/face_detection.py>`_ 
     - `demo_desktop_camera_facedetection.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_camera_facedetection.py>`_ 
     - None, no extra dependencies are needed
     -  
   * - **DNN Face detection** using a YOLOv7 neural network for accurate detection, and detection of small faces.
     - ``run-face-detection-dnn --model yolo7-face.pt``
     - `face_detection_dnn <https://github.com/Social-AI-VU/social-interaction-cloud/blob/main/sic_framework/services/face_detection_dnn/face_detection_dnn.py>`_ 
     - `demo_desktop_camera_facedetection_dnn.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_camera_facedetection_dnn.py>`_ 
     - ``pip install social-interaction-cloud[face-detection-dnn]`` 
     - The model file used in this example can be found here: `yolov7-face.pt <https://drive.google.com/file/d/1oIaGXFd4goyBvB1mYDK24GLof53H9ZYo/view>`_ 
   * - **DNN Face recognition** using a resnet50 network to extract face embeddings and assign an id based on automatic clustering.
     - ``run-face-recognition --model xxx.pt --cascadefile xxx.xml``
     - `face_recognition_dnn <https://github.com/Social-AI-VU/social-interaction-cloud/tree/main/sic_framework/services/face_recognition_dnn>`_ 
     - `demo_desktop_camera_facerecognition.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_camera_facerecognition.py>`_
     - ``pip install social-interaction-cloud[face-recognition]``
     - The cascade classifier file used in this example can be found here\: `haarcascade_frontalface_default.xml <https://github.com/kipr/opencv/blob/master/data/haarcascades/haarcascade_frontalface_default.xml>`_. The model file can be found here\: `resnet50_ft_weight.pt <https://bitbucket.org/socialroboticshub/framework/src/master/sic_framework/services/face_recognition_dnn/resnet50_ft_weight.pt>`_ 
   * - **OpenAI ChatGPT** a text based large language model that provides a very capable dialog agent. Requires a credit card.
     - ``run-gpt `` 
     - `gpt <https://bitbucket.ohttps//github.com/Social-AI-VU/social-interaction-cloud/blob/main/sic_framework/services/openai_gpt/gpt.pyrg/socialroboticshub/framework/src/master/sic_framework/services/openai_gpt/>`_ 
     - `demo_openai_gpt.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_openai_gpt.py>`_ 
     - ``pip install social-interaction-cloud[openai-gpt]``
     - An openai api key can be created here: https://platform.openai.com/api-keys 
   * - **OpenAI Whisper** a powerful speech to text model, capable of running both local and in the cloud. Cloud usage requires a credit card. Start and end recognition is performed using python's `SpeechRecognition <https://pypi.org/project/SpeechRecognition/>`_ 
     - ``run-whisper``
     - `whisper_speech_to_text <https://github.com/Social-AI-VU/social-interaction-cloud/blob/main/sic_framework/services/openai_whisper_speech_to_text/whisper_speech_to_text.py>`_ 
     - `demo_desktop_microphone_whisper.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_microphone_whisper.py>`_ 
     - ``pip install social-interaction-cloud[whisper-speech-to-text]``
     - An openai api key can be created here: https://platform.openai.com/api-keys 
   * - **Google Text to speech** using google cloud API. Requires a credit card. 
     - ``run-google-tts``
     - `text2speech <https://github.com/Social-AI-VU/social-interaction-cloud/blob/main/sic_framework/services/text2speech/text2speech_service.py>`_ 
     - `demo_desktop_google_tts.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_google_tts.py>`_ 
     - ``pip install social-interaction-cloud[google-tts]``
     - A credential keyfile has to be configured\: See https://console.cloud.google.com/apis/api/texttospeech.googleapis.com/. A credit card is required.
   * - Natural language understanding (**NLU**), a joint learning model of intent and slot classification with BERT.
     -  
     - `nlu <https://github.com/Social-AI-VU/social-interaction-cloud/tree/nlu_component/sic_framework/services/nlu>`_ 
     - a simple demo with ASR+NLU pipeline `demo_desktop_asr_nlu.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_asr_nlu.py>`_.
     - git clone & checkout the development branch **nlu_component** ``pip install ."[whisper-speech-to-text,nlu]"``
     -  
   * - **LLM**, A CLI utility and Python library for interacting with Large Language Models, both via remote *APIs* and models that can be installed and run on your own *local* machine. `llm <https://pypi.org/project/llm/>`_ 
     -  
     - `llm <https://github.com/Social-AI-VU/social-interaction-cloud/tree/nlu_component/sic_framework/services/llm>`_ 
     - `demo_desktop_llm.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_llm.py>`_ 
     - git clone & checkout the development branch **nlu_component** ``pip install ."[llm]"``
     - You can use both **free local LLMs** and remote LLMs with your own API keys.
   * - **Templates** for creating your own components
     -  
     - `templates <https://github.com/Social-AI-VU/social-interaction-cloud/tree/main/sic_framework/services/templates>`_ 
     - 
     - 
     - 

    


