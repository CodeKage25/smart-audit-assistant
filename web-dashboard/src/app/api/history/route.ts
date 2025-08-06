import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const historyPath = path.join(process.cwd(), 'data', 'scan_history.json')
    
    try {
      const historyData = await fs.readFile(historyPath, 'utf8')
      const history = JSON.parse(historyData)
      return NextResponse.json(history)
    } catch {
      return NextResponse.json([])
    }
  } catch (error) {
    console.error('History API error:', error)
    return NextResponse.json({ error: 'Failed to load history' }, { status: 500 })
  }
}