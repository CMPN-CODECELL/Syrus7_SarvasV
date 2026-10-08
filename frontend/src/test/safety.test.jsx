import { render,screen } from '@testing-library/react'
import { describe,expect,it } from 'vitest'
import { CompactEvidence, EvidenceView, Status } from '../components/UI'

describe('truthful safety semantics',()=>{
  it('never turns FAILED into VERIFIED',()=>{render(<Status value="FAILED"/>);expect(screen.getByText('FAILED')).toBeInTheDocument();expect(screen.queryByText('VERIFIED')).not.toBeInTheDocument()})
  it('never turns UNKNOWN into MATCHED',()=>{render(<Status value="UNKNOWN"/>);expect(screen.getByText('UNKNOWN')).toBeInTheDocument();expect(screen.queryByText('MATCHED')).not.toBeInTheDocument()})
  it('never turns SAFE_LATE into SUCCESS',()=>{render(<Status value="SAFE_LATE"/>);expect(screen.getByText('SAFE_LATE')).toBeInTheDocument();expect(screen.queryByText('SUCCESS')).not.toBeInTheDocument()})
  it('renders nested backend evidence as labeled visual fields',()=>{const {container}=render(<EvidenceView value={{verified:false,position_diff:[{symbol:'RELIANCE',delta:2}]}}/>);expect(screen.getByText('Verified')).toBeInTheDocument();expect(screen.getByText('Position Diff')).toBeInTheDocument();expect(screen.getByText('RELIANCE')).toBeInTheDocument();expect(container.querySelector('pre')).not.toBeInTheDocument()})
  it('renders dense budget metrics without expanded evidence cards',()=>{const {container}=render(<CompactEvidence value={{limit:100,filled:4,available_buy:96}}/>);expect(screen.getByText('Available Buy')).toBeInTheDocument();expect(screen.getByText('96')).toBeInTheDocument();expect(container.querySelector('.evidence-field')).not.toBeInTheDocument()})
})
