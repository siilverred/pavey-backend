import httpx
import json

url = 'http://localhost:8000/receipt/scan'
image_path = 'C:/Users/Imagination/.gemini/antigravity-ide/brain/06a752ef-4e1d-4735-9956-673f50b4ad3f/.tempmediaStorage/media_06a752ef-4e1d-4735-9956-673f50b4ad3f_1781584922523.png'

with open(image_path, 'rb') as f:
    files = {'file': ('receipt.png', f, 'image/png')}
    data = {'function': 'extract'}
    try:
        response = httpx.post(url, files=files, data=data, timeout=30.0)
        print('Status Code:', response.status_code)
        try:
            print('Response JSON:', json.dumps(response.json(), indent=2))
        except:
            print('Response Text:', response.text)
    except Exception as e:
        print('Error:', e)
