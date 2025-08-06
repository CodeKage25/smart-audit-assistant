import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const { id } = params
    const statusPath = path.join(process.cwd(), 'data', 'status', `${id}.json`)
    
    try {
      const statusData = await fs.readFile(statusPath, 'utf8')
      const status = JSON.parse(statusData)
      return NextResponse.json(status)
    } catch {
      return NextResponse.json({ 
        scanId: id,
        status: 'not_found',
        message: 'Scan not found',
        timestamp: Date.now()
      })
    }
  } catch (error) {
    console.error('Status API error:', error)
    return NextResponse.json({ error: 'Failed to get status' }, { status: 500 })
  }
}