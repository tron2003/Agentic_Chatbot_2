# Agentic Chatbot Frontend

A modern Next.js frontend for the Agentic Chatbot application.

## Features

- 🎨 Modern, responsive UI with Tailwind CSS
- 💬 Real-time chat interface
- 🌙 Dark/light mode support
- 📝 Markdown rendering with syntax highlighting
- 🔄 Real-time typing indicators
- 🎯 Smooth animations and transitions
- 📱 Mobile-friendly design

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn
- Backend chatbot running (default: http://localhost:8000)

### Installation

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Set environment variables (create `.env.local`):
```env
BACKEND_URL=http://localhost:8000
```

4. Start the development server:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000) in your browser.

## API Integration

The frontend communicates with the backend chatbot API through a proxy:

- **Chat endpoint**: `/api/chat` → Backend chat endpoint
- **Configuration**: Set `BACKEND_URL` environment variable to point to your backend

## Development

### Building for Production

```bash
npm run build
npm start
```

### Linting

```bash
npm run lint
```

## Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── api/chat/route.ts    # API proxy endpoint
│   │   ├── globals.css         # Global styles
│   │   ├── layout.tsx          # Root layout
│   │   └── page.tsx            # Main chat interface
│   └── components/             # React components (if needed)
├── public/                     # Static assets
├── tailwind.config.js         # Tailwind configuration
├── tsconfig.json              # TypeScript configuration
└── package.json               # Dependencies and scripts
```

## Styling

The project uses Tailwind CSS with a custom color scheme and includes:

- Custom CSS variables for consistent theming
- Smooth scrolling for chat messages
- Responsive design patterns
- Dark mode support

## Features in Detail

### Chat Interface
- Real-time message display
- User/assistant message distinction
- Timestamps for each message
- Loading states
- Error handling

### Message Formatting
- Markdown rendering
- Syntax highlighting for code blocks
- Support for tables, lists, and other markdown elements
- Custom styling for different content types

### User Experience
- Auto-scroll to latest messages
- Keyboard shortcuts (Enter to send, Shift+Enter for new line)
- Visual feedback for typing states
- Connection indicator
- Clear chat functionality

## Troubleshooting

### Backend Connection Issues
1. Ensure the backend chatbot is running
2. Check the `BACKEND_URL` environment variable
3. Verify the backend API is accessible at the specified URL

### Build Issues
1. Ensure all dependencies are installed
2. Check Node.js version compatibility
3. Clear the `.next` directory and try rebuilding

### Styling Issues
1. Verify Tailwind CSS is properly configured
2. Check if custom CSS variables are being applied
3. Ensure PostCSS is correctly processing the styles

## Contributing

1. Follow the existing code style
2. Use TypeScript for type safety
3. Test thoroughly across different screen sizes
4. Ensure accessibility standards are met