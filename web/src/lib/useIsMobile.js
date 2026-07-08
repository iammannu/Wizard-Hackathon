import { useEffect, useState } from 'react'

// Several page layouts set fixed-column-count grids (e.g. repeat(4,1fr))
// and fixed-width side panels via inline `style={{...}}` — CSS media
// queries can't override an inline style's own properties, so those
// specific spots need a JS-level breakpoint instead. Kept to a single
// shared hook rather than duplicating a resize listener at each call site.
const QUERY = '(max-width: 768px)'

export default function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(QUERY).matches
  )

  useEffect(() => {
    const mql = window.matchMedia(QUERY)
    const onChange = (e) => setIsMobile(e.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return isMobile
}
