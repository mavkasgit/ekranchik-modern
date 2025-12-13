import { useToast } from "@/hooks/use-toast"
import { X } from "lucide-react"

export function Toaster() {
  const { toasts, dismiss } = useToast()

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`
            rounded-lg border px-4 py-3 shadow-lg animate-in slide-in-from-right-full
            ${toast.variant === "destructive" 
              ? "bg-destructive text-destructive-foreground border-destructive" 
              : "bg-background border-border"
            }
          `}
        >
          <div className="flex items-start gap-3">
            <div className="flex-1">
              {toast.title && <p className="font-medium text-sm">{toast.title}</p>}
              {toast.description && <p className="text-sm opacity-90">{toast.description}</p>}
            </div>
            <button onClick={() => dismiss(toast.id)} className="opacity-70 hover:opacity-100">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
