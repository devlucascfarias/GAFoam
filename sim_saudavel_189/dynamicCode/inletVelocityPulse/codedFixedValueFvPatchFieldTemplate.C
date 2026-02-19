/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     | Website:  https://openfoam.org
    \\  /    A nd           | Copyright (C) YEAR OpenFOAM Foundation
     \\/     M anipulation  |
-------------------------------------------------------------------------------
License
    This file is part of OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

\*---------------------------------------------------------------------------*/

#include "codedFixedValueFvPatchFieldTemplate.H"
#include "addToRunTimeSelectionTable.H"
#include "fieldMapper.H"
#include "volFields.H"
#include "surfaceFields.H"
#include "read.H"

//{{{ begin codeInclude

//}}} end codeInclude


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{

// * * * * * * * * * * * * * * * Local Functions * * * * * * * * * * * * * * //

//{{{ begin localCode

//}}} end localCode


// * * * * * * * * * * * * * * * Global Functions  * * * * * * * * * * * * * //

extern "C"
{
    // dynamicCode:
    // SHA1 = 9766e5ebaeb6d35680ebcada61faf090e2d24b29
    //
    // unique function name that can be checked if the correct library version
    // has been loaded
    void inletVelocityPulse_9766e5ebaeb6d35680ebcada61faf090e2d24b29(bool load)
    {
        if (load)
        {
            // code that can be explicitly executed after loading
        }
        else
        {
            // code that can be explicitly executed before unloading
        }
    }
}

// * * * * * * * * * * * * * * Static Data Members * * * * * * * * * * * * * //

makeRemovablePatchTypeField
(
    fvPatchVectorField,
    inletVelocityPulseFixedValueFvPatchVectorField
);


const char* const inletVelocityPulseFixedValueFvPatchVectorField::SHA1sum =
    "9766e5ebaeb6d35680ebcada61faf090e2d24b29";


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

inletVelocityPulseFixedValueFvPatchVectorField::
inletVelocityPulseFixedValueFvPatchVectorField
(
    const fvPatch& p,
    const DimensionedField<vector, volMesh>& iF,
    const dictionary& dict
)
:
    fixedValueFvPatchField<vector>(p, iF, dict)
{
    if (false)
    {
        Info<<"construct inletVelocityPulse sha1: 9766e5ebaeb6d35680ebcada61faf090e2d24b29"
            " from patch/dictionary\n";
    }
}


inletVelocityPulseFixedValueFvPatchVectorField::
inletVelocityPulseFixedValueFvPatchVectorField
(
    const inletVelocityPulseFixedValueFvPatchVectorField& ptf,
    const fvPatch& p,
    const DimensionedField<vector, volMesh>& iF,
    const fieldMapper& mapper
)
:
    fixedValueFvPatchField<vector>(ptf, p, iF, mapper)
{
    if (false)
    {
        Info<<"construct inletVelocityPulse sha1: 9766e5ebaeb6d35680ebcada61faf090e2d24b29"
            " from patch/DimensionedField/mapper\n";
    }
}


inletVelocityPulseFixedValueFvPatchVectorField::
inletVelocityPulseFixedValueFvPatchVectorField
(
    const inletVelocityPulseFixedValueFvPatchVectorField& ptf,
    const DimensionedField<vector, volMesh>& iF
)
:
    fixedValueFvPatchField<vector>(ptf, iF)
{
    if (false)
    {
        Info<<"construct inletVelocityPulse sha1: 9766e5ebaeb6d35680ebcada61faf090e2d24b29 "
            "as copy/DimensionedField\n";
    }
}


// * * * * * * * * * * * * * * * * Destructor  * * * * * * * * * * * * * * * //

inletVelocityPulseFixedValueFvPatchVectorField::
~inletVelocityPulseFixedValueFvPatchVectorField()
{
    if (false)
    {
        Info<<"destroy inletVelocityPulse sha1: 9766e5ebaeb6d35680ebcada61faf090e2d24b29\n";
    }
}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

void inletVelocityPulseFixedValueFvPatchVectorField::updateCoeffs()
{
    if (this->updated())
    {
        return;
    }

    if (false)
    {
        Info<<"updateCoeffs inletVelocityPulse sha1: 9766e5ebaeb6d35680ebcada61faf090e2d24b29\n";
    }

//{{{ begin code
    #line 32 "/home/reynolds-02/interface_openfoam/sim_saudavel_189/0/U/boundaryField/inletGeo"
const scalar t = this->db().time().value();

            const scalar freq = 1.0;        
            const scalar T = 1.0 / freq;   

            const scalar Q_amp = 2.44e-05;

            const scalar tau = fmod(t, T);
            const scalar tE = 0.2 * T;      
            const scalar tA = 0.8 * T;      
            const scalar sigmaE = 0.05 * T; 
            const scalar sigmaA = 0.05 * T; 
            
            const scalar aE = 1.0; 
            const scalar aA = 0.5; 

            scalar E_wave = aE * exp(-pow((tau - tE) / (sigmaE * sqrt(2.0)), 2));
            scalar A_wave = aA * exp(-pow((tau - tA) / (sigmaA * sqrt(2.0)), 2));

            // Vazão Instantânea
            scalar Q_t = Q_amp * (E_wave + A_wave);

            // ===== 3. Geometria e Velocidade =====
            const fvPatch& patch = this->patch();
            const scalar A_inlet = gSum(patch.magSf());

            // Velocidade média
            scalar U_mean = Q_t / A_inlet;
            U_mean = max(U_mean, scalar(0.0)); 

            if (t < T) 
            {
                Info<< "Time:" << t 
                    << " | Area:" << A_inlet 
                    << " | Q:" << Q_t 
                    << " | U_mean:" << U_mean << endl;
            }

            vector U_inlet = vector(0, -U_mean, 0);
            operator==(U_inlet);
//}}} end code

    this->fixedValueFvPatchField<vector>::updateCoeffs();
}


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace Foam

// ************************************************************************* //

