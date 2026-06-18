path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\frontend\src\lib\api.ts"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = "export const modelsApi = {\n    train:   (data: any)    => api.post('/models/train-model', data),\n    list:    ()             => api.get('/models/'),\n    get:     (id: string)   => api.get(`/models/${id}`),\n    predict: (data: { model_id: string; input_data: Record<string, any> }) =>\n      api.post('/models/predict', data),\n  }"

new = """export const modelsApi = {
    train:          (data: any)    => api.post('/models/train-model', data),
    list:           ()             => api.get('/models/'),
    get:            (id: string)   => api.get(`/models/${id}`),
    predict:        (data: { model_id: string; input_data: Record<string, any> }) =>
      api.post('/models/predict', data),
    allGoals:       ()             => api.get('/models/goals/all'),
    availableGoals: (connectionId: string) => api.get(`/models/goals/available/${connectionId}`),
    recommend:      (data: any)    => api.post('/models/goals/recommend', data),
  }"""

if "allGoals" not in content:
    content = content.replace(old, new)
    print("Patched modelsApi")
else:
    print("Already patched")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)