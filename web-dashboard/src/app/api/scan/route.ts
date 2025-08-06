import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import fs from 'fs/promises'
import path from 'path'
import { v4 as uuidv4 } from 'uuid'

const execAsync = promisify(exec)

interface ScanRequest {
  contractPath: string
  includeAI?: boolean
  severity?: 'info' | 'low' | 'medium' | 'high' | 'critical'
  tools?: string[]
  pipeline?: 'fast' | 'thorough' | 'ai-enhanced'
}

interface ScanReport {
  id: string
  path: string
  timestamp: number
  duration: number
  pipeline: string
  static: Array<{
    tool: string
    severity: string
    title: string
    description?: string
    location: string
    confidence?: number
  }>
  ai: Array<{
    severity: string
    title: string
    description: string
    location: string
    confidence: number
    reasoning: string
    suggested_fix?: string
  }>
  metadata: {
    tools_used: string[]
    ai_enabled: boolean
    total_findings: number
    risk_score: number
    gas_optimization_count: number
  }
}

export async function POST(request: NextRequest) {
  const scanId = uuidv4()
  const startTime = Date.now()
  
  try {
    const { 
      contractPath, 
      includeAI = true, 
      severity = 'medium',
      tools = ['slither', 'mythril', 'solhint'],
      pipeline = 'thorough'
    }: ScanRequest = await request.json()

    if (!contractPath) {
      return NextResponse.json({ 
        error: 'Contract path is required',
        code: 'MISSING_PATH'
      }, { status: 400 })
    }

    // Enhanced path validation
    const resolvedPath = await validateContractPath(contractPath)
    if (!resolvedPath.isValid) {
      return NextResponse.json({ 
        error: resolvedPath.error,
        code: 'INVALID_PATH'
      }, { status: 400 })
    }

    await updateScanStatus(scanId, 'running', 'Initializing scan pipeline...')

    
    const report = await executeScanPipeline({
      scanId,
      contractPath: resolvedPath.path!,
      includeAI,
      severity,
      tools,
      pipeline
    })

    // Calculate final metrics
    const duration = Date.now() - startTime
    report.duration = duration
    report.metadata.risk_score = calculateRiskScore(report)

    // Save to history and cache
    await Promise.all([
      saveToHistory(report),
      cacheReport(scanId, report),
      updateScanStatus(scanId, 'completed', 'Scan completed successfully')
    ])

    return NextResponse.json(report)

  } catch (error: any) {
    console.error('Scan API error:', error)
    
    await updateScanStatus(scanId, 'failed', error.message)
    
    return NextResponse.json({ 
      error: error.message || 'Internal server error',
      code: error.code || 'SCAN_FAILED',
      scanId
    }, { status: 500 })
  }
}

async function validateContractPath(contractPath: string): Promise<{
  isValid: boolean
  path?: string
  error?: string
}> {
  try {
    const resolvedPath = path.resolve(contractPath)
    
   
    if (!resolvedPath.includes(process.cwd())) {
      return { isValid: false, error: 'Invalid file path - outside project directory' }
    }
    
    
    const stats = await fs.stat(resolvedPath)
    
    if (stats.isFile()) {
      if (!resolvedPath.endsWith('.sol')) {
        return { isValid: false, error: 'Only .sol files are supported' }
      }
    } else if (stats.isDirectory()) {
      
      const files = await fs.readdir(resolvedPath)
      const solFiles = files.filter(f => f.endsWith('.sol'))
      if (solFiles.length === 0) {
        return { isValid: false, error: 'No .sol files found in directory' }
      }
    } else {
      return { isValid: false, error: 'Path must be a file or directory' }
    }
    
    return { isValid: true, path: resolvedPath }
    
  } catch (error) {
    return { isValid: false, error: 'File or directory not found' }
  }
}

async function executeScanPipeline({
  scanId,
  contractPath,
  includeAI,
  severity,
  tools,
  pipeline
}: {
  scanId: string
  contractPath: string
  includeAI: boolean
  severity: string
  tools: string[]
  pipeline: string
}): Promise<ScanReport> {
  
  const report: ScanReport = {
    id: scanId,
    path: contractPath,
    timestamp: Math.floor(Date.now() / 1000),
    duration: 0,
    pipeline,
    static: [],
    ai: [],
    metadata: {
      tools_used: tools,
      ai_enabled: includeAI,
      total_findings: 0,
      risk_score: 0,
      gas_optimization_count: 0
    }
  }

  try {
    await updateScanStatus(scanId, 'running', 'Running static analysis...')
    
    const staticResults = await runStaticAnalysis({
      contractPath,
      tools,
      severity,
      pipeline
    })
    
    report.static = staticResults
    
    
    if (includeAI) {
      await updateScanStatus(scanId, 'running', 'Running AI analysis...')
      
      const aiResults = await runAIAnalysis({
        contractPath,
        staticResults,
        pipeline,
        severity
      })
      
      report.ai = aiResults
    }
    
   
    await updateScanStatus(scanId, 'running', 'Processing results...')
    
    report.metadata.total_findings = report.static.length + report.ai.length
    report.metadata.gas_optimization_count = countGasOptimizations(report)
    
    return report
    
  } catch (error) {
    throw new Error(`Pipeline execution failed: ${error.message}`)
  }
}

async function runStaticAnalysis({
  contractPath,
  tools,
  severity,
  pipeline
}: {
  contractPath: string
  tools: string[]
  severity: string
  pipeline: string
}) {
  const toolsFlag = tools.join(',')
  const command = `spoon-audit scan "${contractPath}" --no-ai --tools=${toolsFlag} --severity=${severity} --pipeline=${pipeline} --output-format=json`
  
  try {
    const { stdout, stderr } = await execAsync(command, { 
      timeout: pipeline === 'fast' ? 60000 : 180000,
      cwd: process.cwd(),
      env: { 
        ...process.env,
        SPOON_AUDIT_CACHE: 'true',
        SPOON_AUDIT_PARALLEL: pipeline === 'fast' ? 'true' : 'false'
      }
    })
    
    
    const reportPath = path.join(process.cwd(), 'last_report.json')
    const reportData = await fs.readFile(reportPath, 'utf8')
    const cliReport = JSON.parse(reportData)
    
    return cliReport.static || []
    
  } catch (error) {
    console.error('Static analysis failed:', error)
    throw new Error(`Static analysis failed: ${error.message}`)
  }
}

async function runAIAnalysis({
  contractPath,
  staticResults,
  pipeline,
  severity
}: {
  contractPath: string
  staticResults: any[]
  pipeline: string
  severity: string
}) {
  const aiCommand = `spoon-audit ai-analyze "${contractPath}" --context-static --pipeline=${pipeline} --severity=${severity} --multi-model`
  
  try {
    const { stdout, stderr } = await execAsync(aiCommand, { 
      timeout: pipeline === 'fast' ? 90000 : 300000,
      cwd: process.cwd(),
      env: { 
        ...process.env,
        SPOON_AUDIT_AI_ENHANCED: 'true',
        SPOON_AUDIT_CONSENSUS: pipeline === 'ai-enhanced' ? 'true' : 'false'
      }
    })
    
    
    const reportPath = path.join(process.cwd(), 'last_report.json')
    const reportData = await fs.readFile(reportPath, 'utf8')
    const cliReport = JSON.parse(reportData)
    
    return cliReport.ai || []
    
  } catch (error) {
    console.error('AI analysis failed:', error)
    return []
  }
}

async function saveToHistory(report: ScanReport) {
  try {
    const historyPath = path.join(process.cwd(), 'data', 'scan_history.json')
    
    
    await fs.mkdir(path.dirname(historyPath), { recursive: true })
    
    let history = []
    try {
      const historyData = await fs.readFile(historyPath, 'utf8')
      history = JSON.parse(historyData)
    } catch {
      
    }
    
    const historyEntry = {
      id: report.id,
      path: report.path,
      timestamp: report.timestamp,
      duration: report.duration,
      findings_count: report.metadata.total_findings,
      risk_score: report.metadata.risk_score,
      status: 'completed',
      pipeline: report.pipeline,
      ai_enabled: report.metadata.ai_enabled
    }
    
    history.unshift(historyEntry)
    
    
    if (history.length > 100) {
      history = history.slice(0, 100)
    }
    
    await fs.writeFile(historyPath, JSON.stringify(history, null, 2))
    
  } catch (error) {
    console.error('Failed to save to history:', error)
  }
}

async function cacheReport(scanId: string, report: ScanReport) {
  try {
    const cachePath = path.join(process.cwd(), 'data', 'cache', `${scanId}.json`)
    await fs.mkdir(path.dirname(cachePath), { recursive: true })
    await fs.writeFile(cachePath, JSON.stringify(report, null, 2))
  } catch (error) {
    console.error('Failed to cache report:', error)
  }
}

async function updateScanStatus(scanId: string, status: string, message: string) {
  try {
    const statusPath = path.join(process.cwd(), 'data', 'status', `${scanId}.json`)
    await fs.mkdir(path.dirname(statusPath), { recursive: true })
    
    const statusData = {
      scanId,
      status,
      message,
      timestamp: Date.now()
    }
    
    await fs.writeFile(statusPath, JSON.stringify(statusData, null, 2))
  } catch (error) {
    console.error('Failed to update scan status:', error)
  }
}

function calculateRiskScore(report: ScanReport): number {
  const weights = {
    critical: 10,
    high: 7,
    medium: 4,
    low: 2,
    info: 1
  }
  
  let score = 0
  const allFindings = [...report.static, ...report.ai]
  
  allFindings.forEach(finding => {
    const weight = weights[finding.severity as keyof typeof weights] || 1
    const confidence = finding.confidence || 0.8
    score += weight * confidence
  })
  

  return Math.min(Math.round(score), 100)
}

function countGasOptimizations(report: ScanReport): number {
  const gasKeywords = ['gas', 'optimization', 'efficiency', 'cost']
  let count = 0
  
  const allFindings = [...report.static, ...report.ai]
  allFindings.forEach(finding => {
    const text = `${finding.title} ${finding.description || ''}`.toLowerCase()
    if (gasKeywords.some(keyword => text.includes(keyword))) {
      count++
    }
  })
  
  return count
}