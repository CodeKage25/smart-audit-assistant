'use client'
import React, { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Shield, 
  AlertTriangle, 
  CheckCircle, 
  XCircle, 
  Clock, 
  FileText, 
  Zap,
  Brain,
  Eye,
  Download,
  RefreshCw,
  Settings,
  Upload,
  TrendingUp,
  Activity,
  BarChart3,
  Cpu,
  Gauge,
  Target,
  AlertCircle,
  PlayCircle,
  PauseCircle,
  Loader2
} from 'lucide-react'

interface Finding {
  tool?: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  title: string
  description?: string
  location: string
  confidence?: number
  reasoning?: string
  suggested_fix?: string
}

interface ScanReport {
  id: string
  path: string
  timestamp: number
  duration: number
  pipeline: string
  static: Finding[]
  ai: Finding[]
  metadata: {
    tools_used: string[]
    ai_enabled: boolean
    total_findings: number
    risk_score: number
    gas_optimization_count: number
  }
}

interface ScanHistory {
  id: string
  path: string
  timestamp: number
  duration: number
  findings_count: number
  risk_score: number
  status: 'completed' | 'failed' | 'running'
  pipeline: string
  ai_enabled: boolean
}

interface ScanStatus {
  scanId: string
  status: 'running' | 'completed' | 'failed' | 'not_found'
  message: string
  timestamp: number
}

interface Analytics {
  totalScans: number
  totalFindings: number
  averageRiskScore: number
  severityDistribution: Record<string, number>
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

const severityColors = {
  critical: 'bg-red-500',
  high: 'bg-orange-500', 
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
  info: 'bg-blue-500'
}

const severityIcons = {
  critical: XCircle,
  high: AlertTriangle,
  medium: AlertTriangle, 
  low: CheckCircle,
  info: Eye
}

const pipelineOptions = [
  { value: 'fast', label: 'Fast Scan', description: 'Basic checks only', time: '< 1 min' },
  { value: 'thorough', label: 'Thorough Scan', description: 'Comprehensive analysis', time: '2-5 mins' },
  { value: 'ai-enhanced', label: 'AI Enhanced', description: 'Multi-model AI analysis', time: '5-10 mins' }
]

export default function SmartAuditDashboard() {
  const [currentPath, setCurrentPath] = useState('')
  const [currentReport, setCurrentReport] = useState<ScanReport | null>(null)
  const [scanHistory, setScanHistory] = useState<ScanHistory[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [activeTab, setActiveTab] = useState<'scan' | 'history' | 'analytics'>('scan')
  
  // Enhanced scan options
  const [includeAI, setIncludeAI] = useState(true)
  const [pipeline, setPipeline] = useState<'fast' | 'thorough' | 'ai-enhanced'>('thorough')
  const [severity, setSeverity] = useState<'info' | 'low' | 'medium' | 'high' | 'critical'>('medium')
  const [tools, setTools] = useState<string[]>(['slither', 'mythril', 'solhint'])
  
  // Real-time scanning
  const [isScanning, setIsScanning] = useState(false)
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null)
  const [currentScanId, setCurrentScanId] = useState<string | null>(null)

  // File upload
  const [dragActive, setDragActive] = useState(false)

  // Load data on mount
  useEffect(() => {
    loadScanHistory()
    loadLastReport()
    loadAnalytics()
  }, [])

  // Real-time status polling
  useEffect(() => {
    if (currentScanId && isScanning) {
      const interval = setInterval(async () => {
        try {
          const response = await fetch(`/api/status/${currentScanId}`)
          const status = await response.json()
          setScanStatus(status)
          
          if (status.status === 'completed') {
            setIsScanning(false)
            loadScanHistory()
            loadLastReport()
            setCurrentScanId(null)
          } else if (status.status === 'failed') {
            setIsScanning(false)
            setError(status.message)
            setCurrentScanId(null)
          }
        } catch (error) {
          console.error('Failed to get scan status:', error)
        }
      }, 2000)
      
      return () => clearInterval(interval)
    }
  }, [currentScanId, isScanning])

  const loadScanHistory = async () => {
    try {
      const res = await fetch('/api/history')
      const data = await res.json()
      setScanHistory(data)
    } catch (e) {
      console.error('Failed to load scan history')
    }
  }

  const loadLastReport = async () => {
    try {
      const res = await fetch('/api/report')
      const data = await res.json()
      if (data) {
        setCurrentReport(data)
        setCurrentPath(data.path)
      }
    } catch (e) {
      console.error('No previous report found')
    }
  }

  const loadAnalytics = async () => {
    try {
      const res = await fetch('/api/analytics')
      const data = await res.json()
      setAnalytics(data)
    } catch (e) {
      console.error('Failed to load analytics')
    }
  }

  const runScan = async () => {
    if (!currentPath.trim()) {
      setError('Please enter a contract path or upload a file')
      return
    }

    setLoading(true)
    setIsScanning(true)
    setError('')
    setScanStatus(null)

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          contractPath: currentPath,
          includeAI: includeAI,
          severity: severity,
          tools: tools,
          pipeline: pipeline
        })
      })
      
      const data = await res.json()
      
      if (data.error) {
        setError(data.error)
        setIsScanning(false)
      } else {
        setCurrentReport(data)
        setCurrentScanId(data.id)
        loadAnalytics() 
      }
    } catch (e: any) {
      setError(e.message)
      setIsScanning(false)
    } finally {
      setLoading(false)
    }
  }

  const loadHistoryReport = async (historyId: string) => {
    try {
      const res = await fetch(`/api/history/${historyId}`)
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setCurrentReport(data)
        setCurrentPath(data.path)
        setActiveTab('scan')
      }
    } catch (e) {
      setError('Failed to load historical report')
    }
  }

  const exportReport = () => {
    if (!currentReport) return
    
    const dataStr = JSON.stringify(currentReport, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `audit-report-${currentReport.id}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleFileUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      })
      
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setCurrentPath(data.path)
        setError('')
      }
    } catch (e: any) {
      setError('Upload failed: ' + e.message)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    
    const files = Array.from(e.dataTransfer.files)
    const solFile = files.find(file => file.name.endsWith('.sol'))
    
    if (solFile) {
      handleFileUpload(solFile)
    } else {
      setError('Please upload a .sol file')
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
  }, [])

  const getSeverityStats = () => {
    if (!currentReport) return {}
    
    const allFindings = [...currentReport.static, ...currentReport.ai]
    const stats = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
    
    allFindings.forEach(finding => {
      stats[finding.severity] = (stats[finding.severity] || 0) + 1
    })
    
    return stats
  }

  const renderScanInterface = () => (
    <div className="space-y-6">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white rounded-xl shadow-lg p-6 border border-gray-200"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900 flex items-center">
            <Shield className="mr-2 text-blue-600" size={24} />
            AI-Powered Contract Analysis
          </h2>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Cpu size={16} className="text-gray-500" />
              <select
                value={pipeline}
                onChange={(e) => setPipeline(e.target.value as any)}
                className="text-sm border border-gray-300 rounded px-2 py-1"
              >
                {pipelineOptions.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label} ({option.time})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center space-x-2">
              <Target size={16} className="text-gray-500" />
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as any)}
                className="text-sm border border-gray-300 rounded px-2 py-1"
              >
                <option value="info">All Issues</option>
                <option value="low">Low+</option>
                <option value="medium">Medium+</option>
                <option value="high">High+</option>
                <option value="critical">Critical Only</option>
              </select>
            </div>
          </div>
        </div>

        {/* Pipeline Description */}
        <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
          <div className="flex items-center space-x-2">
            <Zap size={16} className="text-blue-600" />
            <span className="text-sm font-medium text-blue-900">
              {pipelineOptions.find(p => p.value === pipeline)?.label}
            </span>
          </div>
          <p className="text-sm text-blue-700 mt-1">
            {pipelineOptions.find(p => p.value === pipeline)?.description}
          </p>
        </div>

        {/* File Input with Drag & Drop */}
        <div 
          className={`relative border-2 border-dashed rounded-lg p-4 transition-colors ${
            dragActive 
              ? 'border-blue-500 bg-blue-50' 
              : 'border-gray-300 hover:border-gray-400'
          }`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="contracts/MyContract.sol or drag & drop files here"
              value={currentPath}
              onChange={(e) => setCurrentPath(e.target.value)}
              className="flex-1 border-0 outline-none bg-transparent text-gray-900 placeholder-gray-500"
              onKeyPress={(e) => e.key === 'Enter' && runScan()}
            />
            <input
              type="file"
              accept=".sol"
              onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
              className="hidden"
              id="file-upload"
            />
            <label
              htmlFor="file-upload"
              className="cursor-pointer flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Upload size={16} />
              <span className="text-sm">Browse</span>
            </label>
          </div>
          
          {dragActive && (
            <div className="absolute inset-0 flex items-center justify-center bg-blue-50 bg-opacity-90 rounded-lg">
              <div className="text-center">
                <Upload size={32} className="text-blue-600 mx-auto mb-2" />
                <p className="text-blue-700 font-medium">Drop .sol file here</p>
              </div>
            </div>
          )}
        </div>

        {/* Advanced Options */}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={includeAI}
              onChange={(e) => setIncludeAI(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700 flex items-center">
              <Brain size={16} className="mr-1" />
              AI Analysis
            </span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={tools.includes('slither')}
              onChange={(e) => {
                if (e.target.checked) {
                  setTools([...tools, 'slither'])
                } else {
                  setTools(tools.filter(t => t !== 'slither'))
                }
              }}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700">Slither</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={tools.includes('mythril')}
              onChange={(e) => {
                if (e.target.checked) {
                  setTools([...tools, 'mythril'])
                } else {
                  setTools(tools.filter(t => t !== 'mythril'))
                }
              }}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700">Mythril</span>
          </label>
        </div>

        {/* Scan Button */}
        <div className="mt-6 flex justify-center">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            disabled={!currentPath.trim() || loading || isScanning}
            onClick={runScan}
            className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-8 py-3 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 font-medium shadow-lg"
          >
            {isScanning ? (
              <>
                <Loader2 className="animate-spin" size={20} />
                <span>Analyzing...</span>
              </>
            ) : loading ? (
              <>
                <RefreshCw className="animate-spin" size={20} />
                <span>Starting...</span>
              </>
            ) : (
              <>
                <PlayCircle size={20} />
                <span>Run Analysis</span>
              </>
            )}
          </motion.button>
        </div>

        {/* Real-time Status */}
        {scanStatus && isScanning && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg"
          >
            <div className="flex items-center space-x-2">
              <Loader2 className="animate-spin text-yellow-600" size={16} />
              <span className="text-sm font-medium text-yellow-800">
                {scanStatus.message}
              </span>
            </div>
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center space-x-2"
          >
            <AlertCircle size={16} />
            <span>{error}</span>
          </motion.div>
        )}
      </motion.div>

      {/* Results */}
      {currentReport && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <ResultsPanel report={currentReport} onExport={exportReport} />
        </motion.div>
      )}
    </div>
  )

  const renderHistoryInterface = () => (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-4"
    >
      <h2 className="text-xl font-semibold text-gray-900 flex items-center">
        <Clock className="mr-2 text-blue-600" size={24} />
        Scan History
      </h2>
      
      <div className="bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Contract
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Pipeline
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Findings
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Risk Score
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Duration
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {scanHistory.map((scan, index) => (
                <motion.tr
                  key={scan.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => loadHistoryReport(scan.id)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <FileText className="mr-2 text-gray-400" size={16} />
                      <div>
                        <span className="text-sm font-medium text-gray-900">
                          {scan.path.split('/').pop()}
                        </span>
                        <div className="flex items-center space-x-2 mt-1">
                          {scan.ai_enabled && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                              <Brain size={10} className="mr-1" />
                              AI
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(scan.timestamp * 1000).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 capitalize">
                      {scan.pipeline}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {scan.findings_count} findings
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <Gauge size={16} className={`${
                        scan.risk_score >= 80 ? 'text-red-500' :
                        scan.risk_score >= 60 ? 'text-orange-500' :
                        scan.risk_score >= 40 ? 'text-yellow-500' :
                        'text-green-500'
                      }`} />
                      <span className="text-sm font-medium">{scan.risk_score}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {scan.duration ? `${Math.round(scan.duration / 1000)}s` : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button className="text-blue-600 hover:text-blue-900">
                      View Report
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </motion.div>
  )

  const renderAnalyticsInterface = () => {
    if (!analytics) {
      return (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="animate-spin text-gray-400" size={32} />
        </div>
      )
    }

    const stats = getSeverityStats()

    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="space-y-6"
      >
        <h2 className="text-xl font-semibold text-gray-900 flex items-center">
          <BarChart3 className="mr-2 text-blue-600" size={24} />
          Analytics & Insights
        </h2>

        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Total Scans"
            value={analytics.totalScans}
            icon={Activity}
            color="blue"
          />
          <MetricCard
            title="Total Findings"
            value={analytics.totalFindings}
            icon={AlertTriangle}
            color="orange"
          />
          <MetricCard
            title="Avg Risk Score"
            value={analytics.averageRiskScore}
            icon={Gauge}
            color="purple"
          />
          <MetricCard
            title="Critical Issues"
            value={analytics.severityDistribution.critical || 0}
            icon={XCircle}
            color="red"
          />
        </div>

        {/* Current Scan Severity Distribution */}
        {currentReport && (
          <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Current Scan Distribution
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              {Object.entries(stats).map(([severity, count]) => {
                const Icon = severityIcons[severity as keyof typeof severityIcons]
                return (
                  <div key={severity} className="text-center">
                    <div className={`p-3 rounded-full ${severityColors[severity as keyof typeof severityColors]} mx-auto w-fit mb-2`}>
                      <Icon className="text-white" size={20} />
                    </div>
                    <p className="text-2xl font-bold text-gray-900">{count}</p>
                    <p className="text-sm text-gray-600 capitalize">{severity}</p>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Top Vulnerabilities */}
        <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">
            Most Common Vulnerabilities
          </h3>
          <div className="space-y-3">
            {analytics.topVulnerabilities.slice(0, 5).map((vuln, index) => (
              <div key={index} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white text-sm font-bold">
                    {index + 1}
                  </div>
                  <div>
                    <span className="text-sm font-medium text-gray-900">{vuln.title}</span>
                    <div className="flex items-center space-x-2 mt-1">
                      <span className={`inline-block w-2 h-2 rounded-full ${severityColors[vuln.avgSeverity as keyof typeof severityColors]}`}></span>
                      <span className="text-xs text-gray-500 capitalize">{vuln.avgSeverity}</span>
                    </div>
                  </div>
                </div>
                <span className="text-sm font-medium text-gray-600">{vuln.count} occurrences</span>
              </div>
            ))}
          </div>
        </div>

        {/* Scan Trends */}
        {analytics.scanTrends.length > 0 && (
          <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Scan Trends (Last 30 Days)
            </h3>
            <div className="h-64 flex items-end justify-between space-x-1">
              {analytics.scanTrends.slice(-14).map((trend, index) => (
                <div key={trend.date} className="flex-1 flex flex-col items-center">
                  <div 
                    className="w-full bg-gradient-to-t from-blue-500 to-purple-500 rounded-t-sm min-h-[4px]"
                    style={{ 
                      height: `${Math.max((trend.scans / Math.max(...analytics.scanTrends.map(t => t.scans))) * 200, 4)}px` 
                    }}
                  ></div>
                  <span className="text-xs text-gray-500 mt-2 transform -rotate-45 origin-left">
                    {new Date(trend.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="flex items-center">
              <Shield className="text-blue-600 mr-3" size={32} />
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  Smart Audit Dashboard
                </h1>
                <p className="text-sm text-gray-600">
                  AI-Powered Smart Contract Security Analysis Pipeline
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              {currentReport && (
                <div className="flex items-center space-x-2 px-3 py-2 bg-gray-100 rounded-lg">
                  <Gauge size={16} className={`${
                    currentReport.metadata.risk_score >= 80 ? 'text-red-500' :
                    currentReport.metadata.risk_score >= 60 ? 'text-orange-500' :
                    currentReport.metadata.risk_score >= 40 ? 'text-yellow-500' :
                    'text-green-500'
                  }`} />
                  <span className="text-sm font-medium">
                    Risk Score: {currentReport.metadata.risk_score}
                  </span>
                </div>
              )}
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-2 text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              >
                <Settings size={20} />
              </motion.button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {[
              { key: 'scan', label: 'Scan', icon: Zap },
              { key: 'history', label: 'History', icon: Clock },
              { key: 'analytics', label: 'Analytics', icon: BarChart3 }
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key as any)}
                className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === key
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon size={16} />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <AnimatePresence mode="wait">
          {activeTab === 'scan' && renderScanInterface()}
          {activeTab === 'history' && renderHistoryInterface()}
          {activeTab === 'analytics' && renderAnalyticsInterface()}
        </AnimatePresence>
      </main>
    </div>
  )
}

// MetricCard Component
interface MetricCardProps {
  title: string
  value: number
  icon: any
  color: 'blue' | 'orange' | 'purple' | 'red' | 'green'
}

function MetricCard({ title, value, icon: Icon, color }: MetricCardProps) {
  const colorClasses = {
    blue: 'bg-blue-500',
    orange: 'bg-orange-500',
    purple: 'bg-purple-500',
    red: 'bg-red-500',
    green: 'bg-green-500'
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className="bg-white rounded-xl shadow-lg p-6 border border-gray-200"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</p>
        </div>
        <div className={`p-3 rounded-full ${colorClasses[color]}`}>
          <Icon className="text-white" size={24} />
        </div>
      </div>
    </motion.div>
  )
}

// Enhanced Results Panel Component
interface ResultsPanelProps {
  report: ScanReport
  onExport: () => void
}

function ResultsPanel({ report, onExport }: ResultsPanelProps) {
  const allFindings = [...report.static, ...report.ai]
  const severityStats = allFindings.reduce((acc, finding) => {
    acc[finding.severity] = (acc[finding.severity] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="bg-white rounded-xl shadow-lg border border-gray-200">
      {/* Enhanced Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-purple-50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 flex items-center">
              <FileText className="mr-2" size={20} />
              Analysis Results
            </h3>
            <div className="flex items-center space-x-4 mt-1">
              <p className="text-sm text-gray-600">
                {report.path.split('/').pop()} • {new Date(report.timestamp * 1000).toLocaleString()}
              </p>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                {report.pipeline} pipeline
              </span>
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                {Math.round(report.duration / 1000)}s duration
              </span>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <Gauge size={20} className={`${
                report.metadata.risk_score >= 80 ? 'text-red-500' :
                report.metadata.risk_score >= 60 ? 'text-orange-500' :
                report.metadata.risk_score >= 40 ? 'text-yellow-500' :
                'text-green-500'
              }`} />
              <span className="text-lg font-bold text-gray-900">
                {report.metadata.risk_score}
              </span>
              <span className="text-sm text-gray-600">risk score</span>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onExport}
              className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium shadow-md hover:bg-blue-700"
            >
              <Download size={16} />
              <span>Export</span>
            </motion.button>
          </div>
        </div>
      </div>

      {/* Metrics Overview */}
      <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{allFindings.length}</p>
            <p className="text-sm text-gray-600">Total Findings</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{report.metadata.gas_optimization_count}</p>
            <p className="text-sm text-gray-600">Gas Issues</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{report.metadata.tools_used.length}</p>
            <p className="text-sm text-gray-600">Tools Used</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{report.ai.length}</p>
            <p className="text-sm text-gray-600">AI Findings</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{report.static.length}</p>
            <p className="text-sm text-gray-600">Static Findings</p>
          </div>
        </div>
      </div>

      {/* Severity Distribution */}
      <div className="px-6 py-4 border-b border-gray-200">
        <h4 className="text-md font-semibold text-gray-900 mb-3">Severity Distribution</h4>
        <div className="flex items-center space-x-6">
          {Object.entries(severityStats).map(([severity, count]) => (
            <div key={severity} className="flex items-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${severityColors[severity as keyof typeof severityColors]}`}></div>
              <span className="text-sm font-medium text-gray-900 capitalize">
                {severity}: {count}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Tools Used */}
      <div className="px-6 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center space-x-4">
          <span className="text-sm font-medium text-gray-700">Tools:</span>
          <div className="flex items-center space-x-2">
            {report.metadata.tools_used.map(tool => (
              <span key={tool} className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-gray-200 text-gray-800">
                {tool}
              </span>
            ))}
            {report.metadata.ai_enabled && (
              <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800">
                <Brain size={12} className="mr-1" />
                AI Enhanced
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Findings Sections */}
      <div className="divide-y divide-gray-200">
        {report.static.length > 0 && (
          <FindingsSection 
            title="Static Analysis" 
            findings={report.static} 
            icon={<Cpu size={16} />}
            color="blue"
          />
        )}
        {report.ai.length > 0 && (
          <FindingsSection 
            title="AI Analysis" 
            findings={report.ai} 
            icon={<Brain size={16} />}
            color="purple"
          />
        )}
      </div>

      {/* No Findings Message */}
      {allFindings.length === 0 && (
        <div className="px-6 py-12 text-center">
          <CheckCircle className="mx-auto h-12 w-12 text-green-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Issues Found</h3>
          <p className="text-gray-600">This contract appears to be secure based on the selected analysis pipeline.</p>
        </div>
      )}
    </div>
  )
}

// Enhanced Findings Section Component
interface FindingsSectionProps {
  title: string
  findings: Finding[]
  icon?: React.ReactNode
  color?: 'blue' | 'purple' | 'green'
}

function FindingsSection({ title, findings, icon, color = 'blue' }: FindingsSectionProps) {
  const [expanded, setExpanded] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  const colorClasses = {
    blue: 'text-blue-600',
    purple: 'text-purple-600',
    green: 'text-green-600'
  }

  const filteredFindings = filter === 'all' 
    ? findings 
    : findings.filter(f => f.severity === filter)

  const severityCounts = findings.reduce((acc, f) => {
    acc[f.severity] = (acc[f.severity] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="px-6 py-4">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center space-x-2 text-left hover:bg-gray-50 rounded-lg p-2 -ml-2"
        >
          <div className="flex items-center space-x-2">
            {icon && <span className={colorClasses[color]}>{icon}</span>}
            <h4 className="text-md font-semibold text-gray-900">
              {title} ({findings.length})
            </h4>
          </div>
          <motion.div
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <AlertTriangle size={16} className="text-gray-400" />
          </motion.div>
        </button>

        {expanded && findings.length > 0 && (
          <div className="flex items-center space-x-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="text-sm border border-gray-300 rounded px-2 py-1"
            >
              <option value="all">All ({findings.length})</option>
              {Object.entries(severityCounts).map(([severity, count]) => (
                <option key={severity} value={severity} className="capitalize">
                  {severity} ({count})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-3"
          >
            {filteredFindings.length === 0 && filter !== 'all' ? (
              <p className="text-gray-500 text-sm py-4 text-center">
                No {filter} severity findings
              </p>
            ) : (
              filteredFindings.map((finding, index) => (
                <FindingCard key={index} finding={finding} />
              ))
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Enhanced Finding Card Component
interface FindingCardProps {
  finding: Finding
}

function FindingCard({ finding }: FindingCardProps) {
  const [expanded, setExpanded] = useState(false)
  const Icon = severityIcons[finding.severity]

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="border border-gray-200 rounded-lg hover:shadow-md transition-all duration-200 overflow-hidden"
    >
      <div 
        className="p-4 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3 flex-1">
            <div className={`p-2 rounded-full ${severityColors[finding.severity]} flex-shrink-0`}>
              <Icon className="text-white" size={16} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2 mb-2">
                <span className={`inline-block px-2 py-1 text-xs font-bold rounded uppercase ${severityColors[finding.severity]} text-white`}>
                  {finding.severity}
                </span>
                {finding.tool && (
                  <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    {finding.tool}
                  </span>
                )}
                {finding.confidence && (
                  <div className="flex items-center space-x-1">
                    <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${finding.confidence * 100}%` }}
                      ></div>
                    </div>
                    <span className="text-xs text-gray-500">
                      {Math.round(finding.confidence * 100)}%
                    </span>
                  </div>
                )}
              </div>
              <h5 className="font-medium text-gray-900 mb-1 line-clamp-2">{finding.title}</h5>
              <p className="text-sm text-gray-600 flex items-center">
                <FileText size={12} className="mr-1 flex-shrink-0" />
                {finding.location}
              </p>
            </div>
          </div>
          <motion.div
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
            className="flex-shrink-0 ml-2"
          >
            <AlertTriangle size={16} className="text-gray-400" />
          </motion.div>
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border-t border-gray-200 bg-gray-50"
          >
            <div className="p-4 space-y-4">
              {finding.description && (
                <div>
                  <h6 className="font-medium text-gray-900 mb-2 flex items-center">
                    <Eye size={14} className="mr-1" />
                    Description
                  </h6>
                  <p className="text-sm text-gray-700 leading-relaxed">{finding.description}</p>
                </div>
              )}
              {finding.reasoning && (
                <div>
                  <h6 className="font-medium text-gray-900 mb-2 flex items-center">
                    <Brain size={14} className="mr-1" />
                    AI Reasoning
                  </h6>
                  <p className="text-sm text-gray-700 leading-relaxed">{finding.reasoning}</p>
                </div>
              )}
              {finding.suggested_fix && (
                <div>
                  <h6 className="font-medium text-gray-900 mb-2 flex items-center">
                    <CheckCircle size={14} className="mr-1" />
                    Suggested Fix
                  </h6>
                  <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                    <p className="text-sm text-green-800 leading-relaxed">{finding.suggested_fix}</p>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
