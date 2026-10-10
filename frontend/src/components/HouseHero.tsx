// Hero illustration for the dashboard: a cut-away home with rooftop solar, drawn in code so it needs no image files.
const pt = (s: number, t: number) => [110 + 410 * s + 270 * t, 290 - 220 * s + 130 * t] as const
const poly = (pts: ReadonlyArray<readonly [number, number]>) => pts.map((p) => p.join(',')).join(' ')

export function HouseHero() {
  const panels = [0, 1, 2, 3].map((i) => {
    const s0 = 0.07 + i * 0.225
    const s1 = s0 + 0.2
    return poly([pt(s0, 0.16), pt(s1, 0.16), pt(s1, 0.66), pt(s0, 0.66)])
  })
  return (
    <svg viewBox="0 0 900 700" role="img" aria-label="Illustration of a home with rooftop solar panels" preserveAspectRatio="xMidYMin meet">
      <defs>
        <linearGradient id="hh-roof" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#eef1ef" /><stop offset="1" stopColor="#c9d0cf" /></linearGradient>
        <linearGradient id="hh-panel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#2a3340" /><stop offset="1" stopColor="#10151d" /></linearGradient>
        <linearGradient id="hh-wallL" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#dfe3e1" /><stop offset="1" stopColor="#c4cbca" /></linearGradient>
        <linearGradient id="hh-room" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#efe6d2" /><stop offset="1" stopColor="#e2d4b6" /></linearGradient>
        <linearGradient id="hh-floor" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#d9a76e" /><stop offset="1" stopColor="#c58f55" /></linearGradient>
        <radialGradient id="hh-glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#ffd98a" stopOpacity="0.55" /><stop offset="1" stopColor="#ffd98a" stopOpacity="0" /></radialGradient>
      </defs>
      {/* ground */}
      <path d="M20 560 Q 200 520 380 590 T 780 520 Q 870 500 890 540 Q 860 640 640 660 Q 380 700 150 650 Q 30 620 20 560Z" fill="#2f6a3a" />
      <path d="M40 575 Q 220 545 380 610 T 770 545 Q 850 535 870 560 Q 830 630 640 645 Q 380 680 160 640 Q 60 615 40 575Z" fill="#3f8a45" />
      {[[60, 590, 26], [95, 575, 20], [790, 560, 28], [840, 548, 22], [815, 585, 18], [150, 625, 16]].map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} fill={i % 2 ? '#4f9d52' : '#3c8444'} />)}
      {/* left wall with window and battery */}
      <polygon points="130,306 380,436 380,600 130,470" fill="url(#hh-wallL)" />
      <g transform="matrix(1 0.52 0 1 130 306)">
        <rect x="52" y="30" width="86" height="82" rx="3" fill="#f3f5f4" />
        <rect x="60" y="38" width="70" height="66" fill="#d9a35e" />
        <rect x="60" y="38" width="70" height="66" fill="url(#hh-glow)" />
        <rect x="93" y="38" width="4" height="66" fill="#f3f5f4" /><rect x="60" y="68" width="70" height="4" fill="#f3f5f4" />
        <rect x="168" y="96" width="46" height="68" rx="3" fill="#f6f7f6" /><rect x="180" y="124" width="22" height="22" rx="2" fill="#555d66" />
      </g>
      {/* open room: back wall, floor, furniture */}
      <polygon points="380,436 790,231 790,395 380,600" fill="url(#hh-room)" />
      <polygon points="380,600 790,395 840,430 430,640" fill="url(#hh-floor)" />
      <polygon points="380,436 380,600 360,600 360,430" fill="#c4cbca" opacity="0.0" />
      <g transform="matrix(1 -0.5 0 1 380 600)">
        <rect x="26" y="-132" width="46" height="132" rx="23" fill="#f6efdd" stroke="#cfc3a6" strokeWidth="3" />
        <rect x="112" y="-132" width="76" height="52" fill="#cda76a" /><rect x="118" y="-126" width="64" height="40" fill="#e8dcc0" />
        <path d="M210 -4 q-8 -50 6 -78 q14 28 6 78z" fill="#4f8f4a" /><path d="M214 -4 q22 -34 38 -40 q0 28 -38 40z" fill="#3f7d3f" /><rect x="206" y="-16" width="24" height="16" rx="3" fill="#b78e56" />
        <rect x="84" y="-52" width="108" height="52" rx="10" fill="#cdbba0" /><rect x="76" y="-62" width="124" height="26" rx="12" fill="#d8c8ae" /><rect x="96" y="-84" width="84" height="40" rx="12" fill="#d3c2a6" />
        <rect x="278" y="-40" width="118" height="40" rx="3" fill="#e9dfc6" /><rect x="262" y="-44" width="150" height="8" rx="2" fill="#d4c5a4" />
        <rect x="292" y="-104" width="100" height="58" rx="3" fill="#161b22" /><rect x="296" y="-100" width="92" height="50" fill="#232b36" />
      </g>
      {/* coffee table and rug on the floor plane */}
      <ellipse cx="560" cy="590" rx="92" ry="30" fill="#e8dcc0" opacity="0.8" />
      <rect x="520" y="560" width="86" height="8" rx="3" fill="#bf9560" /><rect x="526" y="568" width="5" height="26" fill="#a97d49" /><rect x="596" y="568" width="5" height="26" fill="#a97d49" />
      {/* roof slab with solar panels */}
      <polygon points={poly([pt(0, 0), pt(1, 0), pt(1, 1), pt(0, 1)])} fill="url(#hh-roof)" />
      <polygon points="110,290 380,420 380,438 110,308" fill="#aab2b1" />
      <polygon points="380,420 790,215 790,233 380,438" fill="#939b9b" />
      {panels.map((p, i) => <polygon key={i} points={p} fill="url(#hh-panel)" stroke="#8892a0" strokeWidth="2" />)}
      {panels.map((_, i) => {
        const s0 = 0.07 + i * 0.225
        const a = pt(s0 + 0.1, 0.16); const b = pt(s0 + 0.1, 0.66)
        return <line key={`l${i}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#46505f" strokeWidth="1.2" />
      })}
      <line x1={pt(0.07, 0.41)[0]} y1={pt(0.07, 0.41)[1]} x2={pt(0.895, 0.41)[0]} y2={pt(0.895, 0.41)[1]} stroke="#46505f" strokeWidth="1.2" />
      {/* roof ridge highlight */}
      <line x1="110" y1="290" x2="520" y2="70" stroke="#fff" strokeOpacity="0.7" strokeWidth="3" />
    </svg>
  )
}
