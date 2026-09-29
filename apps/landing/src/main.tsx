import React from 'react'
import ReactDOM from 'react-dom/client'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import { useState } from 'react'
import './index.css'
import './responsive.css'

const video = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260723_145606_ab143199-b593-4941-bb1b-9afca215416b.mp4'

const images = [
  'https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260723_152456_65bd59eb-4e9c-4be8-82eb-2aadd5b91e03.png&w=1920&q=85',
  'https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260723_152522_96817909-a45f-4d68-9509-f399dda97419.png&w=1920&q=85',
  'https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260723_152537_150da197-35c4-483c-bd9e-ebcf9335a640.png&w=1920&q=85',
  'https://images.higgs.ai/?default=1&output=webp&url=https%3A%2F%2Fd8j0ntlcm91z4.cloudfront.net%2Fuser_38xzZboKViGWJOttwIXH07lWA1P%2Fhf_20260723_152546_2e114d2c-293d-4c42-89e5-da7eddcfbfa3.png&w=1920&q=85',
]

const cornerClasses = [
  '-top-2 -left-2 border-t-2 border-l-2',
  '-top-2 -right-2 border-t-2 border-r-2',
  '-bottom-2 -left-2 border-b-2 border-l-2',
  '-bottom-2 -right-2 border-b-2 border-r-2',
]

function Brackets({ small = false }: { small?: boolean }) {
  return <>{cornerClasses.map((position) => (
    <span key={position} aria-hidden="true" className={`pointer-events-none absolute ${small ? 'h-3 w-3' : 'h-4 w-4'} border-[#DBDDA1] ${position}`} />
  ))}</>
}

function SelectionHandles() {
  const handles = [
    '-top-1 -left-1', '-top-1 -right-1', '-bottom-1 -left-1', '-bottom-1 -right-1',
    '-top-1 left-1/2 -translate-x-1/2', '-bottom-1 left-1/2 -translate-x-1/2',
    '-left-1 top-1/2 -translate-y-1/2', '-right-1 top-1/2 -translate-y-1/2',
  ]

  return <>
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 z-10 border-2 border-white" />
    {handles.map((position) => <span key={position} aria-hidden="true" className={`pointer-events-none absolute z-20 h-2 w-2 bg-white ${position}`} />)}
  </>
}

function App() {
  const [activeIndex, setActiveIndex] = useState(2)
  const changeIndex = (direction: number) => setActiveIndex((index) => (index + direction + images.length) % images.length)
  const counter = `${String(activeIndex + 1).padStart(2, '0')}/${String(images.length).padStart(2, '0')}`

  return (
    <main className="viewport-scene relative h-screen w-full overflow-hidden bg-[#1a1a1a] text-white">
      <video className="absolute inset-0 h-full w-full object-cover" src={video} autoPlay loop muted playsInline aria-hidden="true" />

      <div className="page-shell relative z-10 flex h-full flex-col justify-between p-5 md:p-12 lg:p-16">
        <header className="flex items-start justify-between">
          <div className="font-jetbrains text-xs tracking-[0.3em]">EpiLocate · 疫影寻灶</div>
          <p className="hidden whitespace-nowrap text-right font-jetbrains text-[10px] leading-relaxed tracking-wider text-white/70 sm:block md:text-xs">
            面向基层医院的新发传染病影像智能辅助诊断系统
          </p>
        </header>

        <section className="hero-section max-w-3xl flex-1 pt-6 md:pt-12" aria-labelledby="headline">
          <h1 id="headline" className="hero-title font-zhongsong text-5xl leading-[0.95] tracking-tight md:text-7xl lg:text-8xl xl:text-[110px]">
            弱监督<br />病灶定位
          </h1>
          <p className="hero-copy mt-6 max-w-md font-zhongsong text-xs leading-relaxed text-[#DBDDA1] md:mt-12 md:text-sm">
            面向新发传染病影像，以图像级或病例级标签研究稳定、可解释的病灶定位。技术路线包括分块掩码粗定位、LIME 精细化与医生反馈。当前为研究原型，不用于临床诊断。
          </p>
          <div className="cta-wrap relative mt-6 w-fit md:mt-12">
            <Brackets />
            <a href="/mvp/" className="cta-button inline-block bg-[#63624B] px-10 py-3.5 font-jetbrains text-xs tracking-[0.2em] text-[#DBDDA1]">
              进入 EpiLocate AI 系统
            </a>
          </div>
        </section>

        <footer className="frame-footer flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <nav className="flex gap-4 md:gap-6" aria-label="浏览画面">
            <div className="relative">
              <Brackets small />
              <button type="button" aria-label="上一张画面" onClick={() => changeIndex(-1)} className="frame-arrow flex h-10 w-10 items-center justify-center bg-[#63624B] text-[#DBDDA1] transition-colors duration-300 hover:bg-[#73725A] md:h-11 md:w-11">
                <ArrowLeft size={18} />
              </button>
            </div>
            <div className="relative">
              <Brackets small />
              <button type="button" aria-label="下一张画面" onClick={() => changeIndex(1)} className="frame-arrow flex h-10 w-10 items-center justify-center bg-[#63624B] text-[#DBDDA1] transition-colors duration-300 hover:bg-[#73725A] md:h-11 md:w-11">
                <ArrowRight size={18} />
              </button>
            </div>
          </nav>

          <div className="frame-stack flex flex-col items-start gap-3 md:items-end md:gap-4">
            <div className="frame-counter font-meutas text-4xl leading-none md:text-7xl lg:text-8xl xl:text-[110px]" aria-live="polite">{counter}</div>
            <div className="frame-gallery scrollbar-hide flex gap-2 overflow-visible md:gap-2.5" aria-label="选择画面">
              {images.map((src, index) => (
                <button type="button" key={src} aria-label={`画面 ${index + 1}`} aria-pressed={index === activeIndex} onClick={() => setActiveIndex(index)} className="relative shrink-0 transition-all duration-300">
                  <img src={src} alt="" className="frame-thumb h-14 w-14 object-cover md:h-20 md:w-20 lg:h-24 lg:w-24" />
                  {index === activeIndex && <SelectionHandles />}
                </button>
              ))}
            </div>
          </div>
        </footer>
      </div>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
)
