import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Builder } from './pages/Builder'
import { Library } from './pages/Library'
import { Review } from './pages/Review'
import { Settings } from './pages/Settings'
import { Status } from './pages/Status'

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Library />} />
        <Route path="/build" element={<Builder />} />
        <Route path="/review/:id" element={<Review />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/status" element={<Status />} />
      </Routes>
    </Layout>
  )
}
