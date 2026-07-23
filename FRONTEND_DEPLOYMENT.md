# Frontend Deployment

Deploy the React app on Vercel as a static Vite site.

## Vercel settings

- Build command: `cd frontend && npm install && npm run build`
- Output directory: `frontend/dist`
- Install command: `cd frontend && npm install`

## Environment variable

Set `VITE_API_URL` in Vercel to your Render backend URL, for example:

- `https://your-render-service.onrender.com`

The frontend reads this value in [frontend/src/App.tsx](frontend/src/App.tsx), so you do not need to hardcode the backend URL.

## Local run

- `cd frontend && npm install && npm run dev`
