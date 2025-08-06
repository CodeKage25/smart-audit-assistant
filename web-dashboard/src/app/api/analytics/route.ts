import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

interface AnalyticsData {
  totalScans: number
  totalFindings: number
  averageRiskScore: number
  severityDistribution: Record<string, number>
  toolUsage: Record<string, number>
  scanTrends: Array<{
    date: string
    scans: number
    findings: number
    avgRiskScore: number
  }>
  topVulnerabilities: Array<{
    title: string
    count: number
    avgSeverity: string
  }>
}

export async function GET(request: NextRequest) {
  try {
    const historyPath = path.join(process.cwd(), 'data', 'scan_history.json')
    
    let history = []
    try {
      const historyData = await fs.readFile(historyPath, 'utf8')
      history = JSON.parse(historyData)
    } catch {
      return NextResponse.json({
        totalScans: 0,
        totalFindings: 0,
        averageRiskScore: 0,
        severityDistribution: {},
        toolUsage: {},
        scanTrends: [],
        topVulnerabilities: []
      })
    }

    // Calculate analytics
    const analytics: AnalyticsData = {
      totalScans: history.length,
      totalFindings: history.reduce((sum: number, scan: any) => sum + (scan.findings_count || 0), 0),
      averageRiskScore: history.length > 0 
        ? Math.round(history.reduce((sum: number, scan: any) => sum + (scan.risk_score || 0), 0) / history.length)
        : 0,
      severityDistribution: {},
      toolUsage: {},
      scanTrends: calculateScanTrends(history),
      topVulnerabilities: []
    }

    // Load detailed reports for more analytics
    const detailedAnalytics = await calculateDetailedAnalytics(history)
    analytics.severityDistribution = detailedAnalytics.severityDistribution
    analytics.topVulnerabilities = detailedAnalytics.topVulnerabilities

    return NextResponse.json(analytics)
    
  } catch (error) {
    console.error('Analytics API error:', error)
    return NextResponse.json({ error: 'Failed to load analytics' }, { status: 500 })
  }
}

function calculateScanTrends(history: any[]): Array<{
  date: string
  scans: number
  findings: number
  avgRiskScore: number
}> {
  const trends: Record<string, any> = {}
  
  history.forEach(scan => {
    const date = new Date(scan.timestamp * 1000).toISOString().split('T')[0]
    
    if (!trends[date]) {
      trends[date] = {
        date,
        scans: 0,
        findings: 0,
        riskScores: []
      }
    }
    
    trends[date].scans++
    trends[date].findings += scan.findings_count || 0
    trends[date].riskScores.push(scan.risk_score || 0)
  })
  
  return Object.values(trends)
    .map((trend: any) => ({
      date: trend.date,
      scans: trend.scans,
      findings: trend.findings,
      avgRiskScore: trend.riskScores.length > 0 
        ? Math.round(trend.riskScores.reduce((a: number, b: number) => a + b, 0) / trend.riskScores.length)
        : 0
    }))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-30) 
}

async function calculateDetailedAnalytics(history: any[]) {
  const severityDistribution: Record<string, number> = {}
  const vulnerabilities: Record<string, { count: number, severities: string[] }> = {}
  
  
  for (const scan of history.slice(0, 50)) { 
    try {
      const cachePath = path.join(process.cwd(), 'data', 'cache', `${scan.id}.json`)
      const reportData = await fs.readFile(cachePath, 'utf8')
      const report = JSON.parse(reportData)
      
      const allFindings = [...(report.static || []), ...(report.ai || [])]
      
      allFindings.forEach((finding: any) => {
        
        severityDistribution[finding.severity] = (severityDistribution[finding.severity] || 0) + 1
        
       
        const key = finding.title.toLowerCase().replace(/[^a-z0-9]/g, ' ').trim()
        if (!vulnerabilities[key]) {
          vulnerabilities[key] = { count: 0, severities: [] }
        }
        vulnerabilities[key].count++
        vulnerabilities[key].severities.push(finding.severity)
      })
      
    } catch (error) {
      continue
    }
  }
  
  const topVulnerabilities = Object.entries(vulnerabilities)
    .map(([title, data]) => ({
      title: title.split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
      count: data.count,
      avgSeverity: getMostCommonSeverity(data.severities)
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
  
  return {
    severityDistribution,
    topVulnerabilities
  }
}

function getMostCommonSeverity(severities: string[]): string {
  const counts: Record<string, number> = {}
  severities.forEach(severity => {
    counts[severity] = (counts[severity] || 0) + 1
  })
  
  return Object.entries(counts)
    .sort(([,a], [,b]) => b - a)[0]?.[0] || 'medium'
}