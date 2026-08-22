/**
 * The one nod to the era (brief §5, "Photography"): Wenger, Mourinho and
 * Benítez as their sides looked when this competition's format was young.
 * Freely licensed only, never a press-agency hotlink, and each image keeps
 * the credit it's licensed to require. Where no photo from the named year
 * clears that bar, the closest licensed one is used and the real year is
 * stated rather than a modern shot standing in for it.
 */

import benitez from '@/assets/managers/benitez.jpg'
import mourinho from '@/assets/managers/mourinho.jpg'
import wenger from '@/assets/managers/wenger.jpg'

export interface ManagerPhoto {
  name: string
  club: string
  year: number
  src: string
  photographer: string
  sourceUrl: string
  license: string
  licenseUrl: string
}

export const MANAGER_PHOTOS: ManagerPhoto[] = [
  {
    name: 'Arsène Wenger',
    club: 'Arsenal',
    year: 2003,
    src: wenger,
    photographer: 'Alexander Ottesen',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Arsene_Wenger.JPG',
    license: 'CC BY-SA 2.5',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/2.5/',
  },
  {
    name: 'José Mourinho',
    club: 'Chelsea',
    year: 2007,
    src: mourinho,
    photographer: 'Mark Freeman',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:JoseMourinho.jpg',
    license: 'CC BY 2.0',
    licenseUrl: 'https://creativecommons.org/licenses/by/2.0/',
  },
  {
    name: 'Rafael Benítez',
    club: 'Liverpool',
    year: 2005,
    src: benitez,
    photographer: 'Djdannyp',
    sourceUrl: 'https://commons.wikimedia.org/wiki/File:Rafael_Benitez.JPG',
    license: 'CC BY-SA 3.0',
    licenseUrl: 'https://creativecommons.org/licenses/by-sa/3.0/',
  },
]
