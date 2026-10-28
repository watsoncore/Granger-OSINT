import { createRoot } from 'react-dom/client'
import App from './App'
import { connectDesktop } from './bridge'
import './styles.css'
import './typography.css'

createRoot(document.getElementById('root')!).render(<App/>)
connectDesktop()
