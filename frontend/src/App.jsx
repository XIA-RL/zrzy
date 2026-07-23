import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Agent from './pages/Agent'
import Solutions from './pages/Solutions'
import SolutionDetail from './pages/SolutionDetail'
import './App.css'

function App() {
  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/solutions" element={<Solutions />} />
        <Route path="/solutions/:moduleId" element={<SolutionDetail />} />
      </Routes>
    </Router>
  )
}

export default App
