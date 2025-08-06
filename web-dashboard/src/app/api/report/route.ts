import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const reportPath = path.join(process.cwd(), 'last_report.json')
    
    try {
      const reportData = await fs.readFile(reportPath, 'utf8')
      const report = JSON.parse(reportData)
      return NextResponse.json(report)
    } catch {
      return NextResponse.json(null)
    }
  } catch (error) {
    console.error('Report API error:', error)
    return NextResponse.json({ error: 'Failed to load report' }, { status: 500 })
  }
}