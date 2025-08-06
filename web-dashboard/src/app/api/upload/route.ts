import { NextRequest, NextResponse } from 'next/server'
import { writeFile, mkdir } from 'fs/promises'
import path from 'path'

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get('file') as File
    
    if (!file) {
      return NextResponse.json({ error: 'No file uploaded' }, { status: 400 })
    }
    
    if (!file.name.endsWith('.sol')) {
      return NextResponse.json({ error: 'Only .sol files are allowed' }, { status: 400 })
    }
    
    // Create uploads directory
    const uploadsDir = path.join(process.cwd(), 'uploads')
    await mkdir(uploadsDir, { recursive: true })
    
    // Save file
    const bytes = await file.arrayBuffer()
    const buffer = Buffer.from(bytes)
    const filePath = path.join(uploadsDir, file.name)
    
    await writeFile(filePath, buffer)
    
    return NextResponse.json({ 
      message: 'File uploaded successfully',
      path: `uploads/${file.name}`,
      filename: file.name
    })
    
  } catch (error) {
    console.error('Upload error:', error)
    return NextResponse.json({ error: 'Upload failed' }, { status: 500 })
  }
}