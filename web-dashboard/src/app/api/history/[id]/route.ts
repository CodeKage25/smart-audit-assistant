import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const { id } = params
    const cachePath = path.join(process.cwd(), 'data', 'cache', `${id}.json`)
    
    try {
      const reportData = await fs.readFile(cachePath, 'utf8')
      const report = JSON.parse(reportData)
      return NextResponse.json(report)
    } catch {
      return NextResponse.json({ error: 'Report not found' }, { status: 404 })
    }
  } catch (error) {
    console.error('History detail API error:', error)
    return NextResponse.json({ error: 'Failed to load report' }, { status: 500 })
  }
}
