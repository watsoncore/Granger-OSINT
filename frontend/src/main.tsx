import { createRoot } from 'react-dom/client'
import App from './App'
import { connectDesktop } from './bridge'
import './styles.css'
import './typography.css'
import './themes.css'
import { restoreTheme } from './themes'

restoreTheme()
createRoot(document.getElementById('root')!).render(<App/>)
connectDesktop()
