import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Workstation } from './pages/Workstation'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Workstation />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
