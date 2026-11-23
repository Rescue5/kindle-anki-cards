import { useId } from "react";

// The silhouette follows the approved drawing. In this coordinate system the
// thumb holds the bail at (49, 244), the flame is at (49, 334), and the feet
// meet the desk at y=444. Light, eyes and hit target use the same anchors.
const silhouette = `
  M237 11 Q243 6 237 53 Q235 90 220 120 L228 122
  Q255 106 315 100 Q327 97 321 107 Q286 164 253 179
  Q259 184 263 186 L257 185 Q262 195 277 200 Q262 210 247 210
  L259 219 L235 220 L242 226 L223 223 L228 227 L210 226
  Q205 229 210 237 Q234 265 248 308 Q250 315 258 322
  Q267 335 259 340 Q253 348 248 341 L245 334 Q246 342 241 339
  Q237 338 237 329 Q231 309 218 290 Q231 322 241 348
  Q258 363 278 351 L268 358 Q287 355 303 337 L296 349
  Q307 341 315 325 L311 337 Q321 318 325 303 L323 319
  Q330 299 338 289 L334 308 Q344 285 355 275 L349 292
  Q363 268 382 257 L370 274 Q394 247 418 246 L406 254
  Q433 242 457 250 L440 250 Q461 250 475 259 L459 256
  Q476 262 487 276 Q462 266 444 285 L457 279
  Q439 291 432 309 L440 298 Q433 313 430 328 L434 318
  Q432 337 421 356 L431 344 Q424 366 401 383 L418 374
  Q402 394 377 405 L390 401 Q372 415 339 416 L352 419
  Q330 423 307 415 L315 421 Q296 419 271 403 L281 413
  Q257 403 243 382 Q249 406 255 431 Q257 440 254 444
  L223 444 Q220 429 237 428 Q233 406 220 395 Q211 385 202 375
  Q198 387 196 402 L194 438 Q194 444 190 444 L157 444
  Q153 431 166 428 Q172 427 178 430 Q183 416 175 393
  Q147 329 155 271 Q132 267 117 260 L77 243 Q69 239 65 246
  Q63 251 60 247 Q57 254 52 249 Q48 254 45 248 Q40 249 39 242
  Q37 230 51 226 Q63 220 80 227 L121 238 Q141 242 155 237
  L167 231 Q172 220 158 215 L133 205 L144 207
  Q117 199 110 187 Q106 182 112 180 Q127 176 132 160
  Q136 138 155 123 Q166 65 219 24 Q229 14 237 11 Z`;

export function FoxFigure() {
  const id = useId();
  const paint = (name: string) => `url(#${id}-${name})`;
  return <svg className="fox-figure" viewBox="0 0 500 450" width="100%" height="100%"
    overflow="visible" aria-hidden="true" focusable="false">
    <defs>
      <radialGradient id={`${id}-mist`}>
        <stop stopColor="#b7b3a9" stopOpacity=".30" />
        <stop offset=".58" stopColor="#9798a0" stopOpacity=".15" />
        <stop offset="1" stopColor="#8e8e99" stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}-light`}>
        <stop stopColor="hsl(var(--lamp-hot))" stopOpacity=".84" />
        <stop offset=".17" stopColor="hsl(var(--lamp-beam))" stopOpacity=".61" />
        <stop offset=".50" stopColor="hsl(var(--lamp-beam))" stopOpacity=".27" />
        <stop offset="1" stopColor="hsl(var(--lamp-beam))" stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}-spill`} gradientUnits="userSpaceOnUse" cx="0" cy="0" r="1">
        <stop stopColor="#ffcd82" stopOpacity=".63" />
        <stop offset=".28" stopColor="#f3b465" stopOpacity=".35" />
        <stop offset=".7" stopColor="#da9b5a" stopOpacity=".11" />
        <stop offset="1" stopColor="#da9b5a" stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}-glass`} cx=".44" cy=".69" r=".85">
        <stop stopColor="#fff5d1" /><stop offset=".36" stopColor="#ffcf78" />
        <stop offset=".76" stopColor="#be792e" /><stop offset="1" stopColor="#6f431f" />
      </radialGradient>
      <linearGradient id={`${id}-brass`}>
        <stop stopColor="#231c16" /><stop offset=".22" stopColor="#64411f" />
        <stop offset=".42" stopColor="#32261b" /><stop offset=".86" stopColor="#19191a" />
        <stop offset="1" stopColor="#76512c" />
      </linearGradient>
    </defs>

    <g pointerEvents="none">
      <ellipse cx="265" cy="242" rx="305" ry="305" fill={paint("mist")} opacity="var(--lamp-glow)" />
      <g fill={paint("light")} opacity="var(--lamp-glow)">
        <g transform="translate(50 333) rotate(-13)" fill={paint("spill")}>
          <path d="M0 -1 A1 1 0 0 0 0 1 Z" transform="scale(570 153)" />
          <path d="M0 -1 A1 1 0 0 1 0 1 Z" transform="scale(155 153)" />
        </g>
        <ellipse cx="50" cy="333" rx="93" ry="95" opacity=".65" />
        <ellipse cx="-25" cy="444" rx="275" ry="7" opacity=".45" />
      </g>
    </g>

    <g strokeLinejoin="round">
      <path d="M28 290 V271 C28 230 72 226 73 271 V290" fill="none" stroke="#27221e" strokeWidth="2.8" />
      <path d="M30 275 Q31 256 38 251" fill="none" stroke="#9c7747" strokeWidth="1" />
      <path d="M22 303 H79 L78 365 H21 Z" fill="#d4c9b4" />
      <path d="M22 303 H79 L78 365 H21 Z" fill={paint("glass")} opacity="var(--lamp-glow)" />
      <path d="M29 306 H34 V357 H29 Z M61 306 H63 V357 H61 Z" fill="#fff1bb" opacity=".30" />
      <path d="M48 352 Q50 347 48 344" fill="none" stroke="#3c2d21" strokeWidth="2" />
      <path d="M45 350 C36 341 48 330 48 316 C56 332 60 341 51 350 L50 343 Z" fill="#fff6d2" opacity="var(--lamp-glow)" />
      <path d="M37 351 H58 L61 360 H34 Z" fill={paint("brass")} />
      <g fill={paint("brass")} stroke="#312216" strokeWidth="1.2">
        <path d="M16 301 L27 291 L38 286 L40 276 H60 L62 286 L73 292 L84 301 Z" />
        <path d="M37 276 L49 266 L50 262 L52 266 L64 275 L60 278 H40 Z" />
        <path d="M20 300 H80 V305 H78 V364 H74 V307 H64 V362 H61 V307 H23 V364 H20 Z" />
        <path d="M22 361 H77 L83 367 Q82 372 50 372 Q20 372 16 369 Z" />
      </g>
      <path d="M19 301 H81 M24 364 H76" fill="none" stroke="#af8145" strokeWidth="1.15" />
      <path d="M43 279 V283 M48 279 V283 M54 279 V283 M58 280 V283" stroke="#ae844c" strokeWidth="1.4" />
    </g>
    <path d={silhouette} fill="#0c0d10" />
    <g className="fox-eyes" fill="#f9e9ce">
      <ellipse cx="142.4" cy="160.7" rx="2.4" ry="4.3" transform="rotate(13 142.4 160.7)" />
      <ellipse cx="177.7" cy="170.6" rx="3.8" ry="4.7" transform="rotate(12 177.7 170.6)" />
    </g>
  </svg>;
}
