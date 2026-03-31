# core/llm_client.py
import base64
from openai import OpenAI

class OpenRouterClient:
    def __init__(self, api_key, model_name):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model_name = model_name

    def _encode_image(self, image_path):
        """Mengubah gambar menjadi format Base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze_screen_structured(self, image_path, prompt, response_model):
        """
        Mengirim gambar dan prompt, lalu memaksa AI menjawab sesuai 
        format response_model (Pydantic).
        """
        base64_image = self._encode_image(image_path)
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
        
        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=messages,
                response_format=response_model
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"[!] LLM Parse Error: {e}")
            return None