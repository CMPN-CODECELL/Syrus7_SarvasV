import { render,screen } from '@testing-library/react'
import { describe,expect,it } from 'vitest'
import { Status } from '../components/UI'

describe('truthful safety semantics',()=>{
  it('never turns FAILED into VERIFIED',()=>{render(<Status value="FAILED"/>);expect(screen.getByText('FAILED')).toBeInTheDocument();expect(screen.queryByText('VERIFIED')).not.toBeInTheDocument()})
  it('never turns UNKNOWN into MATCHED',()=>{render(<Status value="UNKNOWN"/>);expect(screen.getByText('UNKNOWN')).toBeInTheDocument();expect(screen.queryByText('MATCHED')).not.toBeInTheDocument()})
  it('never turns SAFE_LATE into SUCCESS',()=>{render(<Status value="SAFE_LATE"/>);expect(screen.getByText('SAFE_LATE')).toBeInTheDocument();expect(screen.queryByText('SUCCESS')).not.toBeInTheDocument()})
})
