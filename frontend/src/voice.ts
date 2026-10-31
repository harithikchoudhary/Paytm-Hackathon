/** Convert a browser recording to the 16 kHz mono WAV preferred by Sarvam STT. */
export async function prepareSpeechRecording(recording: Blob): Promise<Blob> {
  if (recording.size < 1000) throw new Error('The recording is empty. Hold the mic and speak for a moment before stopping.')
  const context = new AudioContext()
  try {
    const decoded = await context.decodeAudioData(await recording.arrayBuffer())
    if (decoded.duration < 0.7) throw new Error('That recording was too short. Please speak for at least one second.')
    const sampleRate = 16000
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * sampleRate), sampleRate)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    const rendered = await offline.startRendering()
    const samples = rendered.getChannelData(0)
    const averagePower = samples.reduce((total, sample) => total + sample * sample, 0) / samples.length
    if (Math.sqrt(averagePower) < 0.001) throw new Error('I could not hear speech in that recording. Check your microphone and try again.')

    const wav = new ArrayBuffer(44 + samples.length * 2)
    const view = new DataView(wav)
    const writeText = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index++) view.setUint8(offset + index, value.charCodeAt(index))
    }
    writeText(0, 'RIFF')
    view.setUint32(4, wav.byteLength - 8, true)
    writeText(8, 'WAVE')
    writeText(12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, sampleRate, true)
    view.setUint32(28, sampleRate * 2, true)
    view.setUint16(32, 2, true)
    view.setUint16(34, 16, true)
    writeText(36, 'data')
    view.setUint32(40, samples.length * 2, true)
    samples.forEach((sample, index) => {
      const clipped = Math.max(-1, Math.min(1, sample))
      view.setInt16(44 + index * 2, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true)
    })
    return new Blob([wav], { type: 'audio/wav' })
  } finally {
    await context.close()
  }
}
