# React Best Practices

**Version 1.0.0 (Allworth — Vite + React SPA)**

> Guidance for the React + TypeScript frontend. This codebase uses **Vite**,
> **React Router v7**, **MUI**, and **Tailwind CSS** — not Next.js.
> Rules about RSC, Server Actions, `next/dynamic`, `React.cache()`, and SSR
> do not apply here.

---

## 1. Eliminating Waterfalls — CRITICAL

### 1.1 Check Cheap Conditions Before Async Flags
```typescript
// ❌ fetches even if condition is already false
const flag = await getFlag()
if (flag && condition) { ... }

// ✅ skip fetch when condition fails synchronously
if (condition) {
  const flag = await getFlag()
  if (flag) { ... }
}
```

### 1.2 Defer Await Until Needed
```typescript
// ❌ fetches even when skipping
async function handle(userId: string, skip: boolean) {
  const userData = await fetchUser(userId)
  if (skip) return { skipped: true }
  return process(userData)
}

// ✅ only fetch when needed
async function handle(userId: string, skip: boolean) {
  if (skip) return { skipped: true }
  return process(await fetchUser(userId))
}
```

### 1.3 Promise.all() for Independent Operations — CRITICAL (2–10× improvement)
```typescript
// ❌ 3 sequential round trips
const user     = await fetchUser()
const posts    = await fetchPosts()
const comments = await fetchComments()

// ✅ 1 round trip
const [user, posts, comments] = await Promise.all([
  fetchUser(), fetchPosts(), fetchComments()
])
```

### 1.4 Parallelise Partially-Dependent Operations
```typescript
// ❌ config waits for auth
const session = await auth()
const config  = await fetchConfig()

// ✅ config starts immediately alongside auth
const sessionPromise = auth()
const configPromise  = fetchConfig()
const session = await sessionPromise
const [config, data] = await Promise.all([
  configPromise,
  fetchData((await sessionPromise).user.id)
])
```

---

## 2. Bundle Size Optimization — CRITICAL

### 2.1 Lazy-load Heavy Routes with React.lazy
```tsx
// ✅ already applied to Bond Analyzer + Advisor Mailer
const BondAnalyzer = lazy(() => import('./BondAnalyzer'))

<Suspense fallback={<div className="lazy-page-loading" />}>
  <BondAnalyzer />
</Suspense>
```

### 2.2 Preload Based on User Intent
```tsx
function EditorButton({ onClick }: { onClick: () => void }) {
  const preload = () => { void import('./HeavyEditor') }
  return (
    <button onMouseEnter={preload} onFocus={preload} onClick={onClick}>
      Open Editor
    </button>
  )
}
```

---

## 3. Client-Side Data Fetching — MEDIUM-HIGH

### 3.1 Use Passive Event Listeners for Scrolling
```typescript
// ✅ eliminates scroll delay
document.addEventListener('touchstart', handler, { passive: true })
document.addEventListener('wheel', handler, { passive: true })
```

### 3.2 Version and Minimize localStorage Data
```typescript
const VERSION = 'v2'

function saveConfig(config: { theme: string }) {
  try {
    localStorage.setItem(`userConfig:${VERSION}`, JSON.stringify(config))
  } catch { /* incognito / quota exceeded */ }
}

function loadConfig() {
  try {
    const raw = localStorage.getItem(`userConfig:${VERSION}`)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}
```
Always wrap localStorage in try/catch — throws in incognito mode and on quota exceeded.

---

## 4. Re-render Optimization — MEDIUM

### 4.1 Calculate Derived State During Rendering
```tsx
// ❌ unnecessary state + effect
const [fullName, setFullName] = useState('')
useEffect(() => setFullName(`${first} ${last}`), [first, last])

// ✅ derive during render
const fullName = `${first} ${last}`
```

### 4.2 Don't Define Components Inside Components
Creates a new component type on every render — React fully remounts it, destroying state and re-running effects.
```tsx
// ❌ Avatar is a new type on every UserProfile render
function UserProfile({ user, theme }) {
  const Avatar = () => <img src={user.avatarUrl} className={theme} />
  return <Avatar />
}

// ✅ define outside, pass props
function Avatar({ src, theme }: { src: string; theme: string }) {
  return <img src={src} className={theme} />
}
```
Symptoms: input loses focus on keystroke, animations restart, scroll resets.

### 4.3 Use Functional setState Updates
```tsx
// ❌ stale closure; recreated on every items change
const add = useCallback((items) => setItems([...items, ...items]), [items])

// ✅ stable, always reads current state
const add = useCallback((newItems) => setItems(curr => [...curr, ...newItems]), [])
```

### 4.4 Narrow Effect Dependencies
```tsx
// ❌ re-runs on any user field change
useEffect(() => { fetchPosts(user.id) }, [user])

// ✅ re-runs only when id changes
useEffect(() => { fetchPosts(user.id) }, [user.id])
```

### 4.5 Put Interaction Logic in Event Handlers
```tsx
// ❌ effect re-runs on unrelated changes
useEffect(() => { if (submitted) post('/api/register') }, [submitted, theme])

// ✅ run it where it's triggered
function handleSubmit() { post('/api/register') }
```

### 4.6 Split Independent useMemo / useEffect
```tsx
// ❌ sorting re-runs when category changes
const sorted = useMemo(() => {
  const filtered = products.filter(p => p.category === category)
  return filtered.toSorted((a, b) => sortOrder === 'asc' ? a.price - b.price : b.price - a.price)
}, [products, category, sortOrder])

// ✅ independent memos
const filtered = useMemo(() => products.filter(p => p.category === category), [products, category])
const sorted   = useMemo(() => filtered.toSorted(...), [filtered, sortOrder])
```

### 4.7 Use Lazy State Initialization
```tsx
// ❌ JSON.parse runs on every render
const [settings, set] = useState(JSON.parse(localStorage.getItem('s') || '{}'))

// ✅ runs only once
const [settings, set] = useState(() => {
  const raw = localStorage.getItem('s')
  return raw ? JSON.parse(raw) : {}
})
```

### 4.8 Extract Default Non-primitive Values to Constants
```tsx
const NOOP = () => {}
const Avatar = memo(function Avatar({ onClick = NOOP }) { ... })
```

### 4.9 Use useRef for High-frequency Transient Values
```tsx
// ❌ re-renders on every mouse move
const [x, setX] = useState(0)

// ✅ imperatively update the DOM
const dotRef = useRef<HTMLDivElement>(null)
onmousemove = e => { if (dotRef.current) dotRef.current.style.transform = `translateX(${e.clientX}px)` }
```

### 4.10 Use useDeferredValue for Expensive Filtered Renders
```tsx
const deferredQuery = useDeferredValue(query)
const filtered = useMemo(
  () => items.filter(item => fuzzyMatch(item, deferredQuery)),
  [items, deferredQuery]
)
```

### 4.11 Use useTransition Over Manual Loading States
```tsx
const [isPending, startTransition] = useTransition()
const handleSearch = (value: string) => {
  setQuery(value)
  startTransition(async () => setResults(await fetchResults(value)))
}
```

---

## 5. Rendering Performance — MEDIUM

### 5.1 Use Explicit Conditional Rendering
```tsx
// ❌ renders "0" when count is 0
{count && <Badge />}

// ✅
{count > 0 ? <Badge /> : null}
```

### 5.2 CSS content-visibility for Long Lists
```css
.row { content-visibility: auto; contain-intrinsic-size: 0 48px; }
```

### 5.3 Animate a Wrapper div, Not the SVG Directly
```tsx
// ✅ GPU-accelerated on all browsers
<div className="animate-spin"><svg ...></svg></div>
```

### 5.4 Hoist Static JSX Elements
```tsx
const skeleton = <div className="skeleton" />
function Container() { return <div>{loading && skeleton}</div> }
```

---

## 6. JavaScript Performance — LOW-MEDIUM

### 6.1 Build Index Maps for Repeated Lookups
```typescript
// ✅ O(1) vs O(n) per lookup
const userById = new Map(users.map(u => [u.id, u]))
orders.map(o => ({ ...o, user: userById.get(o.userId) }))
```

### 6.2 Use Set for Membership Checks
```typescript
const allowed = new Set(['a', 'b', 'c'])
items.filter(item => allowed.has(item.id))
```

### 6.3 Use toSorted() Instead of sort()
`.sort()` mutates the array and breaks React's immutability model.
```typescript
// ✅
users.toSorted((a, b) => a.name.localeCompare(b.name))
```

### 6.4 Use flatMap Instead of map + filter
```typescript
// ✅ one pass, no intermediate array
users.flatMap(u => u.isActive ? [u.name] : [])
```

### 6.5 Use a Loop for Min/Max Instead of Sort
```typescript
// ✅ O(n) vs O(n log n)
let latest = projects[0]
for (let i = 1; i < projects.length; i++) {
  if (projects[i].updatedAt > latest.updatedAt) latest = projects[i]
}
```

### 6.6 Hoist RegExp Creation
```tsx
// ✅ memoize when pattern changes
const regex = useMemo(() => new RegExp(`(${escapeRegex(query)})`, 'gi'), [query])
```

### 6.7 Early Return from Functions
```typescript
for (const user of users) {
  if (!user.email) return { valid: false, error: 'Email required' }
  if (!user.name)  return { valid: false, error: 'Name required' }
}
return { valid: true }
```

### 6.8 Defer Non-Critical Work
```typescript
requestIdleCallback(() => analytics.track('search', { query }))
```

---

## 7. Advanced Patterns — LOW

### 7.1 Initialize App-level Logic Once
```tsx
let didInit = false
useEffect(() => {
  if (didInit) return
  didInit = true
  loadFromStorage()
}, [])
```

### 7.2 useEffectEvent for Stable Callback Refs
```tsx
import { useEffectEvent } from 'react'

function useWindowEvent(event: string, handler: (e: Event) => void) {
  const onEvent = useEffectEvent(handler)
  useEffect(() => {
    window.addEventListener(event, onEvent)
    return () => window.removeEventListener(event, onEvent)
  }, [event])
}
```

---

## References

- [https://react.dev](https://react.dev)
- [https://vitejs.dev](https://vitejs.dev)
- [https://react.dev/learn/you-might-not-need-an-effect](https://react.dev/learn/you-might-not-need-an-effect)
- [https://react.dev/reference/react/useDeferredValue](https://react.dev/reference/react/useDeferredValue)
- [https://react.dev/reference/react/useTransition](https://react.dev/reference/react/useTransition)
