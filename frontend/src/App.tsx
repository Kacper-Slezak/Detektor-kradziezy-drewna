import { Button } from '@/components/ui/button'

function App() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-4">
      <h1 className="text-2xl font-semibold">Detektor kradzieży drewna</h1>
      <p className="text-muted-foreground">Tailwind + shadcn/ui działają.</p>
      <Button>Przycisk testowy</Button>
    </main>
  )
}

export default App
