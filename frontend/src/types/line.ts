export interface BathStatus {
  bath_number: number
  in_use: boolean
  pallete: number
  in_time: number
  out_time: number
  free?: boolean
  d_time?: number
  article?: string
  color?: string
}

export interface LineStatus {
  baths: BathStatus[]
  timestamp: string
  opcua_connected: boolean
  active_baths?: number
  total_baths?: number
  active_hangers?: number
  power_supply?: { current: number; voltage: number }
}

/** Полезная нагрузка сообщения `line_update`: только счётчики ванн из OPC UA. */
export interface LineUpdatePayload {
  baths?: Array<Pick<BathStatus, 'bath_number' | 'in_use' | 'pallete' | 'in_time' | 'out_time'>>
  timestamp?: string
  opcua_connected?: boolean
  active_hangers?: number
}

export interface CompletedCycle {
  timestamp: string
  pallete: number
  total_time: number
  baths_visited: number[]
}
