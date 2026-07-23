import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Navbar.css'

function navLinkClass(pathname, href) {
  const isActive =
    href === '/'
      ? pathname === '/'
      : pathname === href || pathname.startsWith(`${href}/`)
  return `nav-link${isActive ? ' active' : ''}`
}

function Navbar() {
  const { pathname } = useLocation()

  return (
    <nav className="navbar">
      <div className="navbar-container">
        {/* Logo 区域 */}
        <Link to="/" className="navbar-logo">
          <img src="/logo.png" alt="ZRZY" className="logo-img" />
        </Link>

        {/* 中间菜单 */}
        <div className="navbar-menu">
          <Link to="/" className={navLinkClass(pathname, '/')}>
            首页
          </Link>
          <Link to="/agent" className={navLinkClass(pathname, '/agent')}>
            智能体
          </Link>
          <Link to="/solutions" className={navLinkClass(pathname, '/solutions')}>
            技术方案
          </Link>
          <Link to="/tools" className={navLinkClass(pathname, '/tools')}>
            工具库
          </Link>
        </div>

        {/* 右边认证区 */}
        <div className="navbar-auth">
          <button className="nav-btn login">登录</button>
          <button className="nav-btn signup">注册</button>
        </div>
      </div>
    </nav>
  )
}

export default Navbar
